"""Sanity-check the date extractor against the real scraped corpus.

The scraper's ``fecha_publicacion`` field is empty for 100% of the JSONs
under ``data/normas_completas/``. This test verifies the layered extractor
backfills a publication date for the vast majority of those files without
re-scraping.

Layered coverage observed at implementation time (103 real JSONs):
  - "Publicación:" header              ~9
  - "Texto Original" version            ~28
  - oldest id_version fallback          ~55
  - "<City>, ... de <month> de <year>"  ~9
  - none extractable                    ~2 (one is an index file w/o body)
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.pipelines.date_extraction import extract_fecha_publicacion

NORMAS_DIR = Path(__file__).parent.parent.parent / "data" / "normas_completas"


def _load_real_jsons() -> list[tuple[Path, dict]]:
    if not NORMAS_DIR.exists():
        return []
    out: list[tuple[Path, dict]] = []
    for f in NORMAS_DIR.rglob("*.json"):
        if f.name.endswith(".bak"):
            continue
        try:
            with open(f, encoding="utf-8") as fh:
                out.append((f, json.load(fh)))
        except Exception:
            continue
    return out


@pytest.mark.integration
def test_majority_of_normas_get_a_fecha():
    """At least 90% of real JSONs should yield a publication date."""
    pairs = _load_real_jsons()
    if not pairs:
        pytest.skip("No real corpus under data/normas_completas/")

    populated = sum(1 for _f, d in pairs if extract_fecha_publicacion(d))
    rate = populated / len(pairs)
    # We've measured ~98% in practice; assert a conservative 90% floor so
    # the test still passes if a few edge-case files are added.
    assert rate >= 0.9, (
        f"only {populated}/{len(pairs)} ({rate:.0%}) got a fecha — too low"
    )


@pytest.mark.integration
def test_extracted_dates_are_in_a_plausible_range():
    """Extracted dates must be plausible Chilean publication dates (1900-today)."""
    from datetime import date as date_t
    pairs = _load_real_jsons()
    if not pairs:
        pytest.skip("No real corpus under data/normas_completas/")

    today = date_t.today()
    bad: list[tuple[str, date_t]] = []
    for f, d in pairs:
        fecha = extract_fecha_publicacion(d)
        if fecha is None:
            continue
        if fecha.year < 1900 or fecha > today:
            bad.append((f.name, fecha))
    assert not bad, f"implausible dates extracted: {bad[:5]}"
