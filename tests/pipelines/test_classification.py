"""Tests for norma classification from título."""
from src.pipelines.classification import classify_norma


def test_classify_reglamento_base():
    assert classify_norma("APRUEBA REGLAMENTO DE TRANSFERENCIAS DE POTENCIA") == "reglamento_base"


def test_classify_fija_valores():
    assert classify_norma("FIJA VALORES PARA EL CÁLCULO DE COMA") == "fija_valores"


def test_classify_modifica():
    assert classify_norma("MODIFICA DECRETO SUPREMO N° 62") == "modifica"


def test_classify_deroga():
    assert classify_norma("DEROGA DECRETO SUPREMO N° 100") == "deroga"


def test_classify_unknown_returns_none():
    assert classify_norma("CUALQUIER OTRA COSA") is None


def test_classify_empty_returns_none():
    assert classify_norma("") is None


# Ported from legacy src/search/graph_builder.py: handle scrape duplicates
def test_classify_strips_scrape_duplicate_prefix():
    # Real-world title with duplicated "DECRETO 13" from scraping
    assert classify_norma("DECRETO 13 T FIJA VALORES POR SERVICIOS COMPLEMENTARIOS") == "fija_valores"


def test_classify_with_t_prefix_aprueba_reglamento():
    # Legacy patterns allow optional "T " prefix before action verb
    assert classify_norma("T APRUEBA REGLAMENTO DE COORDINACIÓN") == "reglamento_base"


def test_classify_with_t_prefix_modifica():
    assert classify_norma("T MODIFICA DECRETO SUPREMO") == "modifica"


def test_classify_case_insensitive():
    assert classify_norma("aprueba reglamento de servicios") == "reglamento_base"


def test_classify_fallback_in_first_80_chars():
    # Action verb not at start, but within first 80 chars
    titulo = "DECRETO 100 BIS APRUEBA REGLAMENTO DE COORDINACIÓN Y OPERACIÓN"
    assert classify_norma(titulo) == "reglamento_base"
