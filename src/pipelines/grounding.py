"""Citation extraction and grounding verification.

A response passes grounding iff every [Art. X de NORMA_ID] cite points to an
(id_norma, articulo_numero) actually present in the retrieved docs. Empty
citations also fail (the system prompt mandates citing).
"""
import re

# Citation parser. Accepts several natural variants the LLM produces:
#   [Art. 5 de 1146553]            ← canonical
#   [Art. 5° de 1146553]           ← with degree sign
#   [Artículo 5 de 1146553]        ← full word
#   [Artículo 5° de 1146553]
#   [art. 5° de 1146553]           ← lowercase
#   [Art. 5 bis de 1146553]        ← bis/ter
#   [Art. 36 D de 1146553]         ← letter suffix
#   [Art. primero de 1204012]      ← ORDINAL EN PALABRA (ver abajo)
#
# BUG CORREGIDO 2026-08-08 — artículos numerados con PALABRA no se podían citar.
# El grupo `art` solo aceptaba `\d+`, así que "[Art. primero de 1204012]" no matcheaba:
# `extract_citations` devolvía [] Y `strip_malformed_citations` BORRABA la cita del texto
# mostrado al usuario. No era solo un problema de eval: el sistema eliminaba citas legales
# válidas de la respuesta final.
# Alcance: **267 de 2978 artículos (9%) del corpus** usan ordinal en palabra, en 53 formas
# (PRIMERO/Primero/primero, DECIMOSÉPTIMO, DUODÉCIMO, "primero transitorio", ...).
# Explicaba fallas medidas: DIA ×3 (gold 1204012/primero), Informe Definitivo ×3
# (1160108/segundo), Tránsito (220208/tercero).
# Se usa una LISTA CERRADA de ordinales — no `\w+` — para no legitimar alucinaciones
# tipo "[Art. ag de 1160108]" que `strip_malformed_citations` debe seguir borrando.
_ORDINAL_WORDS = (
    r"(?:d[ée]cimo|undécimo|und[ée]cimo|duod[ée]cimo|decimo)?"      # prefijos compuestos
    r"(?:primero?|segundo?|tercero?|cuarto?|quinto?|sexto?|s[ée]ptimo?|octavo?|noveno?"
    r"|d[ée]cimo|und[ée]cimo|duod[ée]cimo|vig[ée]simo)"
    r"(?:\s+transitorios?)?"                                        # "primero transitorio"
)

CITATION_PATTERN = re.compile(
    r"\["
    r"(?:art[íi]culos?\.?|arts?\.)"                          # Art / Art. / Artículo / Artículos
    r"\s*"
    r"(?P<art>"
    r"\d+\s*[°º]?(?:\s*-\s*\d+)?(?:\s*(?:bis|ter|qu[áa]ter|quinquies))?(?:\s*[A-Z])?"  # +"-M" (72-1, 212-1)
    r"|" + _ORDINAL_WORDS +                                  # ordinal en palabra
    r")"
    r"\s+(?:de|del)\s+"                                      # 'de' or 'del'
    r"(?P<norma>[A-Z_0-9]+)"
    r"\]",
    re.IGNORECASE,
)

_ACCENTS = str.maketrans("áéíóúÁÉÍÓÚ", "aeiouAEIOU")


def _normalize_art(s: str) -> str:
    """Drop degree signs and collapse whitespace so '5°' and '5' match.

    2026-08-08: además case-fold + sin acentos, para que los ordinales en palabra casen
    entre la cita del LLM y la DB ('primero' vs 'PRIMERO', 'decimoséptimo' vs 'DECIMOSÉPTIMO').
    Es inocuo para los numéricos y se aplica a AMBOS lados de toda comparación.
    """
    s = s.replace("°", "").replace("º", "")
    s = re.sub(r"\s*-\s*", "-", s)              # "72 - 1" / "72°-1" → "72-1"
    s = re.sub(r"\s+", " ", s).strip()
    return s.translate(_ACCENTS).lower() if re.search(r"[A-Za-zÁÉÍÓÚáéíóú]", s) else s


def extract_citations(text: str) -> list[tuple[str, str]]:
    """Returns list of (norma_id, articulo_numero_normalized) found in text."""
    return [
        (m.group("norma"), _normalize_art(m.group("art")))
        for m in CITATION_PATTERN.finditer(text)
    ]


def verify_citations(response: str, docs: list[dict]) -> bool:
    """Every citation in `response` must point to an (id_norma, articulo_numero) in docs.

    Articulo numbers are compared with degree sign stripped (so "5" and "5°" match).
    A response with no citations fails grounding (rule from spec).
    """
    cits = extract_citations(response)
    if not cits:
        return False
    valid = {
        (d["id_norma"], _normalize_art(str(d["articulo_numero"])))
        for d in docs
    }
    return all(c in valid for c in cits)


def verify_citations_against_corpus(response: str, conn) -> bool:
    """Looser verifier: citations must exist somewhere in the corpus (DB).

    Use as a fallback after `verify_citations(response, docs)` fails. Distinguishes:
      - Model invented a citation that doesn't exist anywhere → still False here.
      - Model cited a real article whose chunk wasn't in the top-k for this query
        → True (legally valid citation, just a retrieval miss).
    Both checks are strict-exact (no fuzzy). The article number is compared with
    degree sign stripped, same as `verify_citations`.
    """
    cits = extract_citations(response)
    if not cits:
        return False
    with conn.cursor() as cur:
        for norma, art in cits:
            cur.execute(
                "SELECT 1 FROM articulos WHERE id_norma=%s "
                "AND replace(replace(numero,'°',''),'º','')=%s "
                "LIMIT 1",
                (norma, art),
            )
            if cur.fetchone() is None:
                return False
    return True


def strip_malformed_citations(text: str) -> str:
    """Drop `[Art. X de Y]`-shaped brackets whose X isn't a valid article number.

    The strict `CITATION_PATTERN` requires the article identifier to start with
    a digit (with optional ° / bis / letter suffix). When the LLM hallucinates
    a bracket like `[Art. ag de 1160108]`, that's noise in the rendered answer.
    The strict verifier already ignored it; this just hides it from the reader.
    Valid citations are kept verbatim.
    """
    # Loose match for ANY [...Art... de ...] bracket so we can re-test each
    # candidate against the strict pattern. Conservative: only strips brackets
    # that look like a citation attempt but fail the strict format.
    loose = re.compile(
        r"\s*\[(?:art[íi]culos?\.?|arts?\.)[^\]]*\]",
        re.IGNORECASE,
    )
    def _replace(m: re.Match) -> str:
        return m.group(0) if CITATION_PATTERN.match(m.group(0).lstrip()) else ""
    return loose.sub(_replace, text)
