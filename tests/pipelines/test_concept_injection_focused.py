"""Focused-injection behavior (inject_focused_definition flag).

The focused path injects the curated definition (short) labeled with the real
defining article header, REPLACING any full copy of that article in the pool,
so the model copies the right citation instead of a sibling's.
"""
from src.pipelines import concept_injection as ci


def _patch_hit(monkeypatch, hit):
    monkeypatch.setattr(ci, "find_curated_definition", lambda q: hit)


def _set_focused(monkeypatch, value):
    from src.core import config as cfg
    monkeypatch.setattr(cfg.settings, "inject_focused_definition", value,
                        raising=False)


def test_focused_replaces_full_article_with_definition(monkeypatch):
    _patch_hit(monkeypatch, ("250604", "13", "Definición corta del término."))
    _set_focused(monkeypatch, True)
    docs = [
        {"id_norma": "250604", "articulo_numero": "13",
         "articulo_text": "X" * 9000},  # full glossary article
        {"id_norma": "250604", "articulo_numero": "37", "articulo_text": "..."},
    ]
    out = ci.inject_definition("qué es algo", docs)
    # Focused chunk at front, body is the short definition, NOT the 9k block.
    assert out[0]["id_norma"] == "250604"
    assert out[0]["articulo_numero"] == "13"
    assert out[0]["articulo_text"] == "Definición corta del término."
    assert out[0].get("_focused") is True
    # The full art 13 must be gone (replaced, not duplicated).
    assert sum(1 for d in out if d["articulo_numero"] == "13") == 1
    # The sibling (art 37) is preserved.
    assert any(d["articulo_numero"] == "37" for d in out)


def test_focused_prepends_when_article_absent(monkeypatch):
    _patch_hit(monkeypatch, ("1146553", "5", "Otra definición."))
    _set_focused(monkeypatch, True)
    docs = [{"id_norma": "999", "articulo_numero": "1", "articulo_text": "z"}]
    out = ci.inject_definition("qué es x", docs)
    assert out[0]["articulo_text"] == "Otra definición."
    assert len(out) == 2


def test_legacy_path_when_flag_off(monkeypatch):
    _patch_hit(monkeypatch, ("250604", "13", "def"))
    _set_focused(monkeypatch, False)
    docs = [
        {"id_norma": "A", "articulo_numero": "1", "articulo_text": "a"},
        {"id_norma": "250604", "articulo_numero": "13", "articulo_text": "FULL"},
    ]
    out = ci.inject_definition("qué es algo", docs)
    # Legacy: existing full article moved to front, body unchanged.
    assert out[0]["id_norma"] == "250604"
    assert out[0]["articulo_text"] == "FULL"
    assert "_focused" not in out[0]


def test_no_injection_when_no_hit(monkeypatch):
    _patch_hit(monkeypatch, None)
    _set_focused(monkeypatch, True)
    docs = [{"id_norma": "A", "articulo_numero": "1", "articulo_text": "a"}]
    assert ci.inject_definition("hola", docs) == docs


def test_focused_falls_back_when_definition_empty(monkeypatch):
    # Empty curated definition -> focused mode is a no-op-ish: must not inject
    # an empty body; legacy fetch path handles it (here article absent).
    _patch_hit(monkeypatch, ("250604", "13", "   "))
    _set_focused(monkeypatch, True)
    docs = [{"id_norma": "250604", "articulo_numero": "13", "articulo_text": "FULL"}]
    out = ci.inject_definition("qué es algo", docs)
    # Blank definition -> not focused; legacy keeps the full article at front.
    assert out[0]["articulo_text"] == "FULL"
