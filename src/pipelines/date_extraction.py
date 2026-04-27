"""Extract ``fecha_publicacion`` for a norm when the scraper didn't fill it.

The scraped JSONs under ``data/normas_completas/`` have an empty
``fecha_publicacion`` for the entire corpus. Re-scraping is slow and risky,
so this module pulls the publication date from the data we already have:

1. ``fecha_publicacion`` field, if non-empty (most reliable when present).
2. ``Publicación: dd-MES-yyyy`` header in ``texto_completo`` (BCN format).
3. ``versiones[*]`` entry whose ``descripcion`` says "Texto Original" — its
   ``id_version`` (ISO ``YYYY-MM-DD``) is the original publication date.
4. The oldest ``id_version`` across all versions (proxy when no "Texto
   Original" marker exists).
5. ``"<City>, <day> de <month> de <year>"`` signing date inside
   ``texto_completo`` — last-resort proxy (signing precedes publication).
"""
from __future__ import annotations

import re
from datetime import date

# --- Spanish month name maps -------------------------------------------------

SPANISH_MONTHS_FULL = {
    "enero": 1, "febrero": 2, "marzo": 3, "abril": 4, "mayo": 5, "junio": 6,
    "julio": 7, "agosto": 8, "septiembre": 9, "setiembre": 9,
    "octubre": 10, "noviembre": 11, "diciembre": 12,
}

# BCN's "Publicación: 15-MAR-2020" header uses 3-letter Spanish abbreviations.
SPANISH_MONTHS_ABBR = {
    "ENE": 1, "FEB": 2, "MAR": 3, "ABR": 4, "MAY": 5, "JUN": 6,
    "JUL": 7, "AGO": 8, "SEP": 9, "OCT": 10, "NOV": 11, "DIC": 12,
}

# --- Standalone date format parsers -----------------------------------------

ISO_DATE = re.compile(r"^(\d{4})-(\d{1,2})-(\d{1,2})$")
NUMERIC_DATE = re.compile(r"^(\d{1,2})[\.\-/](\d{1,2})[\.\-/](\d{2,4})$")
SPANISH_DATE = re.compile(
    r"(\d{1,2})\s+de\s+(" + "|".join(SPANISH_MONTHS_FULL.keys()) + r")\s+de\s+(\d{4})",
    re.IGNORECASE,
)


def parse_date(s: str) -> date | None:
    """Parse a single date string in any of the supported formats.

    Returns ``None`` for invalid or unrecognised input rather than raising.
    """
    if not s:
        return None
    s = s.strip()

    m = ISO_DATE.match(s)
    if m:
        try:
            return date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        except ValueError:
            return None

    m = NUMERIC_DATE.match(s)
    if m:
        d_, mo, y = int(m.group(1)), int(m.group(2)), int(m.group(3))
        if y < 100:
            y += 2000 if y < 50 else 1900
        try:
            return date(y, mo, d_)
        except ValueError:
            return None

    m = SPANISH_DATE.search(s)
    if m:
        d_ = int(m.group(1))
        mo = SPANISH_MONTHS_FULL[m.group(2).lower()]
        y = int(m.group(3))
        try:
            return date(y, mo, d_)
        except ValueError:
            return None

    return None


# --- In-text patterns for the layered fallbacks -----------------------------

# "Publicación: 15-MAR-2020" — BCN header right above the body.
_PUB_HEADER_RE = re.compile(
    r"Publicaci[oó]n\s*:?\s*(\d{1,2})-([A-ZÁÉÍÓÚ]{3,4})-(\d{4})",
    re.IGNORECASE,
)

_ISO_VERSION_RE = re.compile(r"^(\d{4})-(\d{1,2})-(\d{1,2})$")

# "Santiago, 15 de marzo de 2020" — also matches other Chilean cities
# (Iquique, Valparaíso, ...).
_CITY_DATE_RE = re.compile(
    r"\b[A-ZÁÉÍÓÚÑ][a-záéíóúñ]+(?:\s+[A-ZÁÉÍÓÚÑ][a-záéíóúñ]+)*,\s+"
    r"(\d{1,2})\s+de\s+(" + "|".join(SPANISH_MONTHS_FULL.keys()) + r")\s+de\s+(\d{4})",
    re.IGNORECASE,
)

# Headers / metadata almost always live in the first few KB of texto_completo.
_HEADER_SCAN_LIMIT = 5000

# Plausibility window for any extracted date. Chilean electrical regulation
# corpus starts well after 1900; future-dated entries (e.g. "2222-02-02"
# garbage from the source HTML) must be rejected so the next layer can run.
_MIN_YEAR = 1900
_MAX_YEAR = 2100


def _is_plausible(d: date) -> bool:
    return _MIN_YEAR <= d.year <= _MAX_YEAR


def _from_pub_header(texto: str) -> date | None:
    m = _PUB_HEADER_RE.search(texto[:_HEADER_SCAN_LIMIT])
    if not m:
        return None
    abbr = m.group(2).upper()[:3]
    if abbr not in SPANISH_MONTHS_ABBR:
        return None
    try:
        return date(int(m.group(3)), SPANISH_MONTHS_ABBR[abbr], int(m.group(1)))
    except ValueError:
        return None


def _from_texto_original(versiones: list) -> date | None:
    for v in versiones:
        if not isinstance(v, dict):
            continue
        desc = (v.get("descripcion") or "").strip().lower()
        if "texto original" not in desc:
            continue
        idv = str(v.get("id_version") or "")
        m = _ISO_VERSION_RE.match(idv)
        if not m:
            continue
        try:
            d = date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        except ValueError:
            continue
        if _is_plausible(d):
            return d
    return None


def _from_oldest_version(versiones: list) -> date | None:
    dates: list[date] = []
    for v in versiones:
        if not isinstance(v, dict):
            continue
        idv = str(v.get("id_version") or "")
        m = _ISO_VERSION_RE.match(idv)
        if not m:
            continue
        try:
            d = date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        except ValueError:
            continue
        if _is_plausible(d):
            dates.append(d)
    return min(dates) if dates else None


def _from_city_signing_date(texto: str) -> date | None:
    m = _CITY_DATE_RE.search(texto[:_HEADER_SCAN_LIMIT])
    if not m:
        return None
    mon = m.group(2).lower()
    if mon not in SPANISH_MONTHS_FULL:
        return None
    try:
        return date(int(m.group(3)), SPANISH_MONTHS_FULL[mon], int(m.group(1)))
    except ValueError:
        return None


# --- Public entry point ------------------------------------------------------

def extract_fecha_publicacion(norma_data: dict) -> date | None:
    """Return the publication date for a norm, or ``None`` if undeterminable.

    Tries multiple sources in order of decreasing reliability. See module
    docstring for the full strategy.
    """
    # 1. Existing field
    fp = norma_data.get("fecha_publicacion")
    if fp:
        if isinstance(fp, date):
            return fp
        if isinstance(fp, str):
            d = parse_date(fp)
            if d:
                return d

    texto = norma_data.get("texto_completo") or ""
    versiones = norma_data.get("versiones") or []

    # 2. "Publicación: dd-MES-yyyy" header
    d = _from_pub_header(texto)
    if d:
        return d

    # 3. "Texto Original" version's id_version
    d = _from_texto_original(versiones)
    if d:
        return d

    # 4. Oldest id_version across all versions
    d = _from_oldest_version(versiones)
    if d:
        return d

    # 5. "<City>, dd de mes de yyyy" signing-date proxy
    d = _from_city_signing_date(texto)
    if d:
        return d

    return None
