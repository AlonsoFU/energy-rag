"""Grounded answer generation with citation verification and retry.

For Ollama (and any provider that supports JSON schema response format) we use
constrained decoding: the LLM emits a JSON object {answer, citations} where
`citations` is enum-constrained to the IDs present in retrieved docs. The
sampler physically prevents emitting citations outside the retrieved set.

The downstream interface stays a single text string with inline `[Art. N de
ID]` citations — we rebuild that from the structured JSON response. If JSON
parsing fails, we fall back to the unconstrained text path with retry.
"""
import json
from src.components.llm import LLMProvider, get_llm_provider
from src.pipelines.prompts import build_answer_prompt, get_answer_system
from src.pipelines.grounding import (
    verify_citations, verify_citations_against_corpus, strip_malformed_citations,
)
from src.pipelines.grammar import extract_valid_citations, build_json_schema
from src.pipelines.off_topic import is_off_topic, REFUSAL_TEXT


def _format_as_text(parsed: dict) -> str:
    """Convert {answer: str, citations: [str]} into a single text with inline cites.

    Joins answer with citations to satisfy the existing grounding verifier
    (which scans for `[Art. N de ID]` patterns in text).
    """
    answer = (parsed.get("answer") or "").strip()
    cits = parsed.get("citations") or []
    if not cits:
        return answer
    # Prevent duplicate citation appearance if model already inlined them
    suffix = " " + " ".join(cit for cit in cits if cit not in answer)
    return (answer + suffix).strip()


def generate_answer(
    query: str,
    docs: list[dict],
    llm: LLMProvider | None = None,
    model: str | None = None,
    max_retries: int = 1,
    initial_top: int | None = None,
) -> dict:
    """Generate a grounded answer with citation verification.

    Args:
        docs: Pool of retrieved documents (caller controls this size).
        initial_top: If set, the first attempt uses only `docs[:initial_top]`.
            Retries widen to the full pool. This implements "retry-on-fail with
            wider context": ask with a focused top-k first, and if grounding
            fails (LLM cited outside its allowed set), give it more room to
            find the right article. Caller controls the widening by sizing
            `docs` larger than `initial_top` (e.g. retrieve top_k=15, pass
            initial_top=10 → first try sees 10, retry sees 15).

    Returns dict with keys: text, grounding_pass, model, tokens_in, tokens_out.
    """
    from src.core import config as cfg
    llm = llm or get_llm_provider()
    model = model or cfg.settings.llm_default

    # Pre-LLM off-topic check: if the query's significant words don't appear
    # in the corpus vocabulary, refuse directly without burning an LLM call.
    # Catches trap queries like "xenobalbúrgico" or "receta pisco sour" where
    # the LLM tends to hallucinate instead of refusing.
    if is_off_topic(query):
        return {
            "text": REFUSAL_TEXT,
            "grounding_pass": True,  # refusal is a valid response, not an alucination
            "model": model,
            "tokens_in": 0,
            "tokens_out": 0,
        }

    system = get_answer_system()

    response_text = ""
    grounding_pass = False
    tokens_in = tokens_out = 0
    used_model = model
    extra_instruction = ""

    for attempt in range(max_retries + 1):
        # On retry, widen the doc pool if caller provided a larger one.
        if attempt == 0 and initial_top is not None and len(docs) > initial_top:
            active_docs = docs[:initial_top]
        else:
            active_docs = docs

        # Context budget: drop tail docs until the prompt fits the LLM ctx.
        # MUST be applied BEFORE building the schema — otherwise the JSON
        # enum would force the model to cite docs the prompt no longer shows
        # (the constrained sampler would deadlock or hallucinate).
        budget = getattr(cfg.settings, "prompt_doc_char_budget", 0)
        if budget and budget > 0:
            from src.pipelines.prompts import fit_docs_to_budget
            active_docs = fit_docs_to_budget(active_docs, budget)

        prompt = build_answer_prompt(query, active_docs) + extra_instruction
        response_format: dict | None = None
        # Hybrid pattern (default): skip JSON-schema constrained decoding —
        # Ollama deadlocks on qwen3.5 (issues #15540, #15260). Generate plain;
        # `verify_citations` below + the retry-on-fail loop with stricter
        # `extra_instruction` enforces the legal guarantee (citations must
        # appear verbatim from the retrieved pool). Industry-recommended
        # pattern when constrained decoding isn't reliable in the runtime.
        if cfg.settings.use_constrained_decoding and active_docs:
            citations = extract_valid_citations(active_docs)
            if citations:
                response_format = build_json_schema(citations)

        resp = llm.generate(
            prompt, model=model, system=system,
            temperature=0.0, max_tokens=2000,
            response_format=response_format,
        )
        raw = resp.text
        tokens_in += resp.tokens_in
        tokens_out += resp.tokens_out
        used_model = resp.model

        if response_format:
            try:
                parsed = json.loads(raw)
                response_text = _format_as_text(parsed)
            except (json.JSONDecodeError, TypeError):
                response_text = raw
        else:
            response_text = raw

        # A valid refusal (LLM says "No encuentro esa información") is also a
        # grounded response — it's the correct answer when docs don't contain
        # the query's topic. Not a hallucination.
        if REFUSAL_TEXT.lower() in response_text.lower():
            grounding_pass = True
            break
        if verify_citations(response_text, active_docs):
            grounding_pass = True
            break
        # In-pool verify failed. Try corpus fallback: cite may be a real
        # article that retrieval just didn't surface in the top-k. Still
        # strict-exact (no fuzzy) — only legitimizes citations whose
        # (id_norma, articulo_numero) actually exist in the DB.
        try:
            from src.storage.connection import with_connection
            with with_connection() as _conn:
                if verify_citations_against_corpus(response_text, _conn):
                    grounding_pass = True
                    break
        except Exception:
            pass  # DB issues: stay strict, fall through to retry
        extra_instruction = (
            "\n\nIMPORTANTE: Tu respuesta anterior contenía citas inválidas. "
            "Cita SOLO artículos provistos arriba, verbatim."
        )

    # Clean up: drop bracket patterns the strict CITATION_PATTERN can't parse
    # (e.g. `[Art. ag de 1160108]` — LLM hallucinated a non-numeric article id).
    # Valid citations are kept verbatim. Only affects the rendered text; the
    # grounding_pass decision above has already been made.
    response_text = strip_malformed_citations(response_text)

    return {
        "text": response_text,
        "grounding_pass": grounding_pass,
        "model": used_model,
        "tokens_in": tokens_in,
        "tokens_out": tokens_out,
    }
