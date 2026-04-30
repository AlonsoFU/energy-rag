"""Grounded answer generation with citation verification and retry.

Calls the LLM with the answer prompt; if the response fails grounding, retries
once with a corrective addendum. Returns text plus a `grounding_pass` flag and
accumulated token counts across attempts.

For Ollama models we additionally constrain decoding with a GBNF grammar
generated from the retrieved docs — the model is physically prevented from
emitting citations outside the retrieved set. Non-Ollama providers receive
no grammar (constraint enforced via tool use / json schema elsewhere).
"""
from src.components.llm import LLMProvider, get_llm_provider
from src.pipelines.prompts import build_answer_prompt, get_answer_system
from src.pipelines.grounding import verify_citations
from src.pipelines.grammar import extract_valid_citations, build_gbnf_grammar


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

    # Build grammar only when applicable: Ollama target + non-empty doc set.
    # Empty docs would yield an unusable grammar; non-Ollama providers can't
    # consume GBNF (their constraint path is JSON schema / tool use).
    grammar: str | None = None
    if docs and model.startswith("ollama/"):
        citations = extract_valid_citations(docs)
        gbnf = build_gbnf_grammar(citations)
        grammar = gbnf or None

    response_text = ""
    grounding_pass = False
    tokens_in = tokens_out = 0
    used_model = model
    prompt = base_prompt

    for attempt in range(max_retries + 1):
        resp = llm.generate(
            prompt, model=model, system=system,
            temperature=0.0, max_tokens=2000,
            grammar=grammar,
        )
        response_text = resp.text
        tokens_in += resp.tokens_in
        tokens_out += resp.tokens_out
        used_model = resp.model
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
