"""Query expansion strategies for the COMPLEJO retrieval branch.

Three techniques:
- :func:`hyde`: generate a hypothetical answer document so the embedding
  search lands closer to the relevant articulos.
- :func:`multi_query`: produce 3 paraphrases to cover different surface
  vocabulary in BM25.
- :func:`step_back`: abstract the query to a more general formulation,
  useful for synthesising across multiple normas.

All use the configured LLM provider with the Haiku model by default.
"""
from src.components.llm import LLMProvider, get_llm_provider


HYDE_PROMPT = """Eres un experto en normativa eléctrica chilena. Genera una respuesta hipotética en estilo de artículo legal (3-5 oraciones, vocabulario técnico) a la siguiente pregunta. La respuesta no necesita ser correcta, solo plausible y rica en términos técnicos del dominio para mejorar la búsqueda.

Pregunta: {query}

Respuesta hipotética:"""

MULTIQUERY_PROMPT = """Genera 3 reformulaciones distintas de la siguiente pregunta sobre normativa eléctrica chilena. Una pregunta por línea, sin numeración, sin viñetas.

Pregunta original: {query}

Reformulaciones:"""

STEPBACK_PROMPT = """Dada esta pregunta específica sobre normativa eléctrica chilena, reformúlala como una pregunta más general/abstracta sobre el mismo tema. Devuelve solo la pregunta reformulada, sin explicaciones.

Pregunta específica: {query}

Pregunta general:"""

# Reformulación SELECTIVA (PreQRAG 2025 / "not all queries need rewriting"):
# un solo call condicional que reescribe SOLO las queries en lenguaje cotidiano
# a registro legal formal. Las queries ya-legales devuelven "IGUAL" → no se tocan.
# Aditivo y vector-only en el retriever (la query original sigue en BM25/rerank),
# así que reescribir de más una query ya-formal no la daña.
SELECTIVE_REFORM_PROMPT = (
    "Eres experto en normativa eléctrica chilena. Si la siguiente pregunta está en "
    "lenguaje COTIDIANO/coloquial, reescríbela en términos legales formales del sector "
    "eléctrico (organismos, conceptos, artículos relevantes). Si la pregunta YA usa "
    "lenguaje legal/técnico, responde EXACTAMENTE la palabra: IGUAL.\n"
    "No expliques. Solo la reescritura o IGUAL.\n"
    "Pregunta: {query}\nReescritura:"
)


# Inferencia del CONCEPTO legal implícito (estándar legal IR 2025: "transformar el
# hecho informal en hecho legal por interpretación"; papers STARD / "Exploiting LLMs'
# Reasoning to Infer Implicit Concepts"). Distinto a selective_reform (parafraseo
# verboso que aluciná números de ley): aquí el LLM devuelve SOLO los términos
# técnico-legales EXACTOS del dominio, cortos, SIN inventar leyes/organismos. Ataca el
# muro de vocabulario (ej "tope de ganancia"→"tasa de descuento"). Aditivo vector-only.
INFER_CONCEPT_PROMPT = (
    "Eres experto en la normativa eléctrica chilena (LGSE y reglamentos). La siguiente "
    "pregunta está en lenguaje cotidiano. Identifica los TÉRMINOS TÉCNICO-LEGALES exactos "
    "que la LEY usaría para el concepto de la pregunta.\n"
    "REGLAS ESTRICTAS:\n"
    "- Devuelve SOLO términos, separados por coma. Máximo 8 palabras en total.\n"
    "- NO inventes números de ley, decretos, artículos ni nombres de organismos.\n"
    "- NO escribas oraciones ni expliques. Solo los términos legales.\n"
    "Pregunta: {query}\nTérminos legales exactos:"
)


def infer_legal_concept(query: str, llm: LLMProvider | None = None,
                        model: str | None = None) -> str:
    """Infiere los términos técnico-legales EXACTOS del concepto implícito en una
    query coloquial. Devuelve "" si el LLM no aporta nada útil. Pensado para uso
    ADITIVO vector-only (caller embebe ``query + " " + terms``)."""
    llm, model = _resolve(llm, model)
    resp = llm.generate(INFER_CONCEPT_PROMPT.format(query=query), model=model, max_tokens=40)
    terms = resp.text.strip()
    # Saneamiento: 1 línea, sin números de ley alucinados (filtra tokens "ley N", "DFL N").
    terms = terms.splitlines()[0].strip() if terms else ""
    import re as _re
    terms = _re.sub(r"(?i)\b(ley|decreto|dfl|dl|art[íi]culo|d\.?f\.?l\.?)\s*n?[°º]?\s*[\d\.\-]+", "", terms)
    terms = _re.sub(r"\s{2,}", " ", terms).strip(" ,;.")
    if len(terms) <= 3:
        return ""
    return terms


def _resolve(llm: LLMProvider | None, model: str | None) -> tuple[LLMProvider, str]:
    from src.core import config as cfg
    return llm or get_llm_provider(), model or cfg.settings.llm_haiku


def hyde(query: str, llm: LLMProvider | None = None, model: str | None = None) -> str:
    """Hypothetical Document Embeddings: generate a fake answer to embed."""
    llm, model = _resolve(llm, model)
    resp = llm.generate(HYDE_PROMPT.format(query=query), model=model, max_tokens=300)
    return resp.text.strip()


def multi_query(query: str, llm: LLMProvider | None = None, model: str | None = None) -> list[str]:
    """Generate up to 3 paraphrased variants of the query."""
    llm, model = _resolve(llm, model)
    resp = llm.generate(MULTIQUERY_PROMPT.format(query=query), model=model, max_tokens=200)
    return [line.strip() for line in resp.text.splitlines() if line.strip()][:3]


def step_back(query: str, llm: LLMProvider | None = None, model: str | None = None) -> str:
    """Step-back prompting: abstract the query to a more general one."""
    llm, model = _resolve(llm, model)
    resp = llm.generate(STEPBACK_PROMPT.format(query=query), model=model, max_tokens=100)
    return resp.text.strip()


def selective_reform(query: str, llm: LLMProvider | None = None, model: str | None = None) -> str:
    """Reformula la query coloquial a registro legal formal, o "" si ya es formal.

    Devuelve la reescritura legal SOLO cuando la query es coloquial; si el LLM
    responde "IGUAL" (o algo trivialmente corto) devuelve "" → el caller deja la
    query intacta. Pensado para uso ADITIVO vector-only en el retriever: el caller
    embebe ``query + " " + reform`` y mantiene la query original en BM25/rerank,
    así reescribir de más una query ya-formal es inocuo (restatement casi idéntico).
    """
    llm, model = _resolve(llm, model)
    resp = llm.generate(SELECTIVE_REFORM_PROMPT.format(query=query), model=model, max_tokens=60)
    rw = resp.text.strip()
    if rw.upper() == "IGUAL" or len(rw) <= 3:
        return ""
    return rw
