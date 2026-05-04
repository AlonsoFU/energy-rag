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
from src.pipelines.grounding import verify_citations
from src.pipelines.grammar import extract_valid_citations, build_json_schema


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
) -> dict:
    """Generate a grounded answer with citation verification.

    Returns dict with keys: text, grounding_pass, model, tokens_in, tokens_out.
    """
    from src.core import config as cfg
    llm = llm or get_llm_provider()
    model = model or cfg.settings.llm_default

    system = get_answer_system()
    base_prompt = build_answer_prompt(query, docs)

    # Build JSON schema only when we have docs; an empty enum would force
    # the model into impossible territory.
    response_format: dict | None = None
    if docs:
        citations = extract_valid_citations(docs)
        if citations:
            response_format = build_json_schema(citations)

    response_text = ""
    grounding_pass = False
    tokens_in = tokens_out = 0
    used_model = model
    prompt = base_prompt

    for attempt in range(max_retries + 1):
        resp = llm.generate(
            prompt, model=model, system=system,
            temperature=0.0, max_tokens=2000,
            response_format=response_format,
        )
        raw = resp.text
        tokens_in += resp.tokens_in
        tokens_out += resp.tokens_out
        used_model = resp.model

        # When response_format was applied, parse JSON to natural-text form.
        if response_format:
            try:
                parsed = json.loads(raw)
                response_text = _format_as_text(parsed)
            except (json.JSONDecodeError, TypeError):
                # Fallback: treat raw as text. Verifier may still find inline cites.
                response_text = raw
        else:
            response_text = raw

        if verify_citations(response_text, docs):
            grounding_pass = True
            break
        # On failure, escalate prompt
        prompt = base_prompt + (
            "\n\nIMPORTANTE: Tu respuesta anterior contenía citas inválidas. "
            "Cita SOLO artículos provistos arriba, verbatim."
        )

    return {
        "text": response_text,
        "grounding_pass": grounding_pass,
        "model": used_model,
        "tokens_in": tokens_in,
        "tokens_out": tokens_out,
    }
