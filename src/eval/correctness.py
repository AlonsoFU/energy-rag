"""Hard correctness scoring for in_domain definitional queries.

The runner's `answered`/`grounding_pass`/`recall+art` are GUARDRAILS, not a
measure of answer quality:
  - `recall+art = 100%` is true *by construction* once `inject_curated_
    definitions` prepends the defining article — it no longer detects misses.
  - `grounding_pass` only checks citations point into the retrieved pool
    (near-tautological under the hybrid pattern).
  - `answered` only checks the model did not emit the refusal sentinel.

This module answers a sharper question for the 273 in_domain queries:

  1. **cited_expected** (binary, EXACT): does the answer cite the expected
     defining article `(expected_norma, expected_articulo)`? No fuzzy.
  2. **definition_recall** (continuous in [0,1]): what fraction of the
     glossary definition's content words appear in the answer? Measures
     whether the answer is FAITHFUL to the curated definition rather than
     hallucinating or dodging. (High partly by construction — the defining
     article is injected — so it mostly catches the model NOT using it.)

Both are reported as a distribution, not a single magic threshold, so the
number is honest.
"""
from __future__ import annotations

import re
import unicodedata

# Spanish function words + the most common verbs/connectors that appear in
# almost every legal definition. Removing them keeps `definition_recall`
# focused on the substantive terms ("subestaciones", "radiales", ...) instead
# of being inflated by "de la que se".
_STOPWORDS = {
    "a", "al", "algo", "alguna", "algunas", "alguno", "algunos", "ante",
    "antes", "aquel", "aquella", "aquellas", "aquello", "aquellos", "asi",
    "aun", "aunque", "cada", "como", "con", "contra", "cual", "cuales",
    "cuando", "cuanto", "cuya", "cuyas", "cuyo", "cuyos", "de", "del", "desde",
    "donde", "dos", "el", "ella", "ellas", "ello", "ellos", "en", "entre",
    "era", "eran", "eres", "es", "esa", "esas", "ese", "eso", "esos", "esta",
    "esta", "estaba", "estan", "estar", "estas", "este", "esto", "estos",
    "fin", "fue", "fueron", "ha", "haber", "habia", "hacer", "hacia", "han",
    "hasta", "hay", "la", "las", "le", "les", "lo", "los", "mas", "mediante",
    "mientras", "muy", "ni", "no", "nos", "o", "para", "pero", "por", "porque",
    "que", "se", "sea", "sean", "segun", "ser", "si", "sin", "sino", "sobre",
    "solo", "son", "su", "sus", "tal", "tales", "tan", "tanto", "te", "toda",
    "todas", "todo", "todos", "tras", "un", "una", "unas", "uno", "unos", "y",
    "ya", "esten", "este", "sera", "seran", "asimismo", "dicho", "dicha",
    "dichos", "dichas", "respectiva", "respectivo", "respectivas",
    "respectivos", "decir", "denomina", "denominan", "entendera", "entiende",
    "entendera", "considera", "consideran", "corresponde", "corresponden",
}

_TOKEN_RE = re.compile(r"[a-zñ0-9]+")


def _strip_accents(s: str) -> str:
    s = unicodedata.normalize("NFKD", s)
    return "".join(c for c in s if not unicodedata.combining(c))


def content_tokens(text: str) -> set[str]:
    """Lowercase, de-accent, split on non-alphanumerics, drop stopwords and
    tokens shorter than 3 chars. Returns a SET (we measure recall of distinct
    content words, not term frequency)."""
    if not text:
        return set()
    norm = _strip_accents(text.lower())
    return {
        t for t in _TOKEN_RE.findall(norm)
        if len(t) >= 3 and t not in _STOPWORDS
    }


def definition_recall(answer: str, definition: str) -> float:
    """Fraction of the definition's content words present in the answer.

    Returns 0.0 when the definition has no content words (cannot score).
    """
    def_toks = content_tokens(definition)
    if not def_toks:
        return 0.0
    ans_toks = content_tokens(answer)
    return len(def_toks & ans_toks) / len(def_toks)


def _norm_art(value) -> str:
    """Match deepeval_runner._norm_articulo: drop degree signs / whitespace."""
    if value is None:
        return ""
    return str(value).strip().replace("°", "").replace("º", "")


def cited_expected(citations, expected_norma, expected_articulo) -> bool:
    """EXACT: is `(expected_norma, expected_articulo)` among the citations?

    `citations` is a list of `(norma_id, articulo)` as produced by
    `grounding.extract_citations` / stored in the eval rows. Articulo is
    compared with degree-sign normalization only — no fuzzy.
    """
    if expected_norma is None:
        return False
    target = (str(expected_norma), _norm_art(expected_articulo))
    for c in citations or []:
        norma = str(c[0])
        art = _norm_art(c[1]) if len(c) > 1 else ""
        if (norma, art) == target:
            return True
    return False
