"""exp #78: aviso deterministico cuando NINGUNA cita se verifico.

Medido 2026-09-16 sobre qonly2_dev + qonly2_holdout: 13 respuestas cayeron a prosa y
NINGUNA uso lenguaje de duda, pese a que el prompt pide "si las citas no responden la
pregunta, dilo". El aviso no es un porcentaje de confianza (mal calibrado = +2% y mas
sesgo de automatizacion, ver docs/bitacora/investigacion-abstencion-2026-09-16.md seccion 19):
es el hecho binario "hubo o no hubo calce literal contra el articulo".

INVARIANTE QUE PROTEGEN ESTOS TESTS: el aviso no debe alterar el scoring del eval.
`score_answer` saca `refuso` por substring de REFUSAL_TEXT y las citas por
extract_citations (patron de corchetes). Si el aviso llevara corchetes o el texto de
rechazo, moveria cita_ok/cita_limpia/precision sin que nadie lo note.
"""
from unittest.mock import MagicMock

from src.core import config as cfg
from src.pipelines.generate import generate_answer
from src.pipelines.grounding import extract_citations
from src.pipelines.off_topic import REFUSAL_TEXT

DOCS = [{"id_norma": "DECRETO_62", "articulo_numero": "1",
         "articulo_text": "Se define potencia firme como la capacidad de suministro."}]


def _llm(text):
    fake = MagicMock()
    fake.generate.return_value = MagicMock(text=text, tokens_in=10, tokens_out=5, model="m")
    return fake


def _prosa_llm():
    # JSON sin cita verificable => _quote_first no valida nada => cae a prosa.
    return _llm('{"answer": "La potencia firme se define asi", '
                '"citations": ["[Art. 1 de DECRETO_62]"]}')


def test_flag_off_no_agrega_aviso(monkeypatch):
    monkeypatch.setattr(cfg.settings, "answer_prosa_marcar", False)
    r = generate_answer("?", DOCS, llm=_prosa_llm())
    assert "SIN CITA VERIFICADA" not in r["text"]


def test_flag_on_marca_la_prosa(monkeypatch):
    monkeypatch.setattr(cfg.settings, "answer_prosa_marcar", True)
    r = generate_answer("?", DOCS, llm=_prosa_llm())
    assert r["cita_verificada"] is False
    assert r["text"].startswith("SIN CITA VERIFICADA")


def test_cita_verificada_no_lleva_aviso(monkeypatch):
    """Si quote-only emitio citas verificadas, la respuesta NO se marca."""
    monkeypatch.setattr(cfg.settings, "answer_prosa_marcar", True)
    monkeypatch.setattr(cfg.settings, "answer_quote_first", True)
    monkeypatch.setattr(cfg.settings, "answer_quote_only", True)
    r = generate_answer("?", DOCS, llm=_llm("[Art. 1 de DECRETO_62] «Se define potencia firme»"))
    if r["cita_verificada"]:                       # ruta quote-only
        assert "SIN CITA VERIFICADA" not in r["text"]
    else:                                          # si no verifico, DEBE ir marcada
        assert r["text"].startswith("SIN CITA VERIFICADA")


def test_aviso_no_ensucia_el_scoring_del_eval(monkeypatch):
    """El aviso no puede aportar citas ni parecer un rechazo (rompria el eval)."""
    monkeypatch.setattr(cfg.settings, "answer_prosa_marcar", True)
    aviso = cfg.settings.answer_prosa_aviso
    assert extract_citations(aviso) == []
    assert REFUSAL_TEXT.lower() not in aviso.lower()
    assert "[" not in aviso and "]" not in aviso


def test_citas_del_cuerpo_sobreviven_al_aviso(monkeypatch):
    """Las citas que ya estaban se siguen extrayendo con el aviso delante."""
    monkeypatch.setattr(cfg.settings, "answer_prosa_marcar", True)
    r = generate_answer("?", DOCS, llm=_prosa_llm())
    assert ("DECRETO_62", "1") in [(str(n), str(a)) for n, a in extract_citations(r["text"])]
