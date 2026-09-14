"""exp #77: reatribucion de citas por procedencia en `_quote_first`.

Casos tomados del diagnostico real del 17 % de held-out que caia a prosa.
"""
from types import SimpleNamespace

import pytest

from src.core import config as cfg
from src.pipelines.generate import _quote_first

GLOSARIO = ("Artículo 13: Para los efectos del presente reglamento se entenderá por:\n"
            "Decreto 70, ENERGÍA\nArt. primero N° 8, i)\nD.O. 05.06.2024\n"
            "    d) Central Renovable con Capacidad de Regulación: Central de generación renovable "
            "que utiliza recursos primarios variables, con la capacidad de gestionar temporalmente su recurso.")
MORA = ("Artículo 3.- Para efectos de esta ley, se entenderá por Mora el estado en que un Usuario de "
        "Sistema Interoperable tiene deudas impagas en un plazo igual o inferior a 5 años.")
FRASE_G = "Central Renovable con Capacidad de Regulación: Central de generación renovable que utiliza recursos primarios variables"
FRASE_M = "se entenderá por Mora el estado en que un Usuario de Sistema Interoperable tiene deudas impagas"

DOCS = [{"id_norma": "250604", "articulo_numero": "13", "articulo_text": GLOSARIO},
        {"id_norma": "1207690", "articulo_numero": "3", "articulo_text": MORA}]


class FakeLLM:
    def __init__(self, text):
        self.text = text

    def generate(self, *a, **k):
        return SimpleNamespace(text=self.text, tokens_in=0, tokens_out=0, model="fake")


def correr(text, docs=DOCS):
    qs, _ = _quote_first("q", docs, FakeLLM(text), "m", 2)
    return qs


@pytest.fixture
def reatribuir(monkeypatch):
    monkeypatch.setattr(cfg.settings, "answer_quote_reatribuir", True, raising=False)


def test_flag_apagado_conserva_el_comportamiento_viejo(monkeypatch):
    monkeypatch.setattr(cfg.settings, "answer_quote_reatribuir", False, raising=False)
    assert correr(f"[Art. primero N° 8, d)] «{FRASE_G}»") == []


def test_etiqueta_tomada_de_la_nota_bcn_se_reatribuye(reatribuir):
    assert correr(f"[Art. primero N° 8, d)] «{FRASE_G}»") == [("13", "250604", FRASE_G)]


def test_articulo_inventado_se_reatribuye_al_doc_real(reatribuir):
    assert correr(f"[Art. 17 de 1207690] «{FRASE_M}»") == [("3", "1207690", FRASE_M)]


def test_etiqueta_correcta_no_cambia(reatribuir):
    assert correr(f"[Art. 3 de 1207690] «{FRASE_M}»") == [("3", "1207690", FRASE_M)]


def test_frase_en_dos_docs_se_rechaza(reatribuir):
    dup = DOCS + [{"id_norma": "999", "articulo_numero": "1", "articulo_text": MORA}]
    assert correr(f"[Art. primero N° 8] «{FRASE_M}»", dup) == []


def test_frase_que_no_esta_en_ningun_doc_se_rechaza(reatribuir):
    assert correr("[Art. 13 de 250604] «esta frase no aparece en ningun articulo del corpus dado»") == []


def test_frase_corta_se_rechaza(reatribuir):
    assert correr("[Art. primero N° 8, d)] «Central Renovable»") == []
