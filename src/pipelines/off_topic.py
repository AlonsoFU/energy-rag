"""Off-topic detector — refuses queries whose significant words don't appear
in the corpus vocabulary.

Useful for trap queries like "xenobalbúrgico" or "receta del pisco sour" where
the LLM tends to hallucinate by latching onto loosely-related retrieved docs
instead of refusing. The check runs BEFORE the LLM call, so it costs nothing
and is deterministic.
"""
import re
from functools import lru_cache

from src.storage.connection import with_connection


_TOKEN_RE = re.compile(r"\b[a-záéíóúñü]{4,}\b", re.IGNORECASE)

# Common Spanish stopwords + question/verb words that show up in queries
_STOPWORDS = {
    "para", "como", "cual", "cuales", "donde", "cuando", "porque", "porqué",
    "puede", "pueden", "debe", "deben", "esta", "este", "están", "esto",
    "una", "uno", "unos", "unas", "del", "las", "los", "que", "qué",
    "sobre", "según", "entre", "hace", "hacer", "tiene", "tienen",
    "ante", "ser", "son", "sea", "fue", "han", "más", "menos",
}


@lru_cache(maxsize=1)
def _corpus_vocab() -> frozenset[str]:
    """Build the corpus vocabulary from all articulo texts. Cached forever
    in-process — corpus changes are rare and reloading the module re-fetches.
    """
    with with_connection() as conn, conn.cursor() as cur:
        cur.execute("SELECT texto FROM articulos")
        words: set[str] = set()
        for (text,) in cur.fetchall():
            words.update(m.group(0).lower() for m in _TOKEN_RE.finditer(text))
        # Also treat curated concept names + aliases as in-vocabulary. A
        # glossary alias (e.g. "PELP" for "Planificación Energética") is by
        # definition a domain term, but the corpus body may only ever spell
        # out the full name — so the acronym would be flagged off-topic and
        # the query refused before the alias can fire. Legal-safe: aliases
        # are human-curated, not fuzzy.
        cur.execute("SELECT nombre, aliases FROM conceptos")
        for nombre, aliases in cur.fetchall():
            for blob in (nombre, *(aliases or [])):
                if blob:
                    words.update(
                        m.group(0).lower() for m in _TOKEN_RE.finditer(blob)
                    )
    return frozenset(words)


def is_off_topic(query: str, min_oov_ratio: float = 0.5) -> bool:
    """Return True if more than `min_oov_ratio` of the query's significant
    words are out-of-vocabulary against the corpus.

    A query is "significant words" = lowercased, ≥4 chars, alpha, non-stopword.
    """
    tokens = {m.group(0).lower() for m in _TOKEN_RE.finditer(query)}
    significant = tokens - _STOPWORDS
    if not significant:
        return False  # too short to judge; let LLM handle it

    vocab = _corpus_vocab()
    oov = significant - vocab
    return len(oov) / len(significant) > min_oov_ratio


REFUSAL_TEXT = "No encuentro esa información en las normas disponibles."
