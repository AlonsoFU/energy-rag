"""Constrained-decoding helpers: extract valid citations from retrieved docs
and build either a GBNF grammar (Ollama) or a JSON schema (API providers).

The same `(articulo, id_norma)` list feeds both targets — call sites pick the
output format based on the LLM provider, so the rest of the pipeline stays
LLM-agnostic.
"""


def extract_valid_citations(docs: list[dict]) -> list[tuple[str, str]]:
    """Return sorted unique [(articulo_numero, id_norma), ...] from docs.

    Format is preserved verbatim ('5°' stays '5°') because grammars must
    match what the article header literally says.
    """
    citations = set()
    for d in docs:
        articulo = str(d["articulo_numero"]).strip()
        norma = str(d["id_norma"]).strip()
        citations.add((articulo, norma))
    return sorted(citations)


def build_gbnf_grammar(citations: list[tuple[str, str]]) -> str:
    """Build a GBNF grammar that allows free text plus a closed set of citations.

    Returns empty string when there are no citations — caller decides whether
    to fall back to unconstrained generation.

    Grammar shape:
        root     ::= ( non-bracket | citation )*
        non-bracket ::= [^\\x5b]   # any char except '['
        citation ::= "[Art. <ART> de <NORMA>]" | ...

    `\\x5b` is '[' in hex. Used to bypass GBNF's own use of '[' for char classes.
    """
    if not citations:
        return ""

    citation_alts = " | ".join(
        f'"[Art. {art} de {norma}]"' for art, norma in citations
    )
    return (
        "root ::= ( non-bracket | citation )*\n"
        "non-bracket ::= [^\\x5b]\n"
        f"citation ::= {citation_alts}\n"
    )


def build_json_schema(citations: list[tuple[str, str]]) -> dict:
    """Build a JSON schema that constrains citations to the provided set.

    Used with API providers that support `response_format` with json_schema
    (OpenAI, Anthropic via tools). The `enum` field on the citations array
    item enforces verbatim membership.
    """
    enum_values = [f"[Art. {art} de {norma}]" for art, norma in citations]
    return {
        "type": "object",
        "properties": {
            "answer": {"type": "string"},
            "citations": {
                "type": "array",
                "items": {"type": "string", "enum": enum_values},
            },
        },
        "required": ["answer", "citations"],
    }
