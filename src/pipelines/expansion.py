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
