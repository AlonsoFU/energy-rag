"""Deterministic citation anchoring (_anchor_authoritative_citation).

Closes the attribution gap: when a query centers on a single curated concept
whose authoritative article A is known, but the answer cited nothing from A's
norma, append a curated citation to A. Guarded against general-vs-detalle: if
the answer already cited A's norma, leave it untouched.
"""
import src.pipelines.concept_injection as ci
from src.pipelines.generate import _anchor_authoritative_citation


def _patch(monkeypatch, ret):
    monkeypatch.setattr(ci, "find_subject_concept", lambda q: ret)


def test_appends_when_authoritative_norma_not_cited(monkeypatch):
    # Concept resolves to LGSE 258171/212; answer cited only the reglamento.
    _patch(monkeypatch, ("258171", "212", "def", "Coordinador", None))
    txt = "El Coordinador opera el sistema [Art. 13 de 250604]."
    out = _anchor_authoritative_citation("qué es el Coordinador", txt)
    assert "[Art. 212 de 258171]" in out
    assert txt in out  # original prose preserved


def test_noop_when_authoritative_norma_already_cited(monkeypatch):
    # Guard: the answer already cites the authoritative norma (even another art)
    # → do NOT override (general-vs-detalle, e.g. AVI method in the reglamento).
    _patch(monkeypatch, ("258171", "212", "def", "Coordinador", None))
    txt = "El Coordinador... [Art. 208 de 258171]."
    assert _anchor_authoritative_citation("qué es el Coordinador", txt) == txt


def test_noop_when_no_single_concept(monkeypatch):
    # Relational / ambiguous query → find_subject_concept returns None → no anchor.
    _patch(monkeypatch, None)
    txt = "Comparación... [Art. 2 de 1160108]."
    assert _anchor_authoritative_citation("relación entre A y B", txt) == txt


def test_anchors_when_no_citation_at_all(monkeypatch):
    _patch(monkeypatch, ("258171", "72", "def", "Coordinado", None))
    txt = "Los Coordinados son quienes operan centrales."
    out = _anchor_authoritative_citation("qué es Coordinado", txt)
    assert "[Art. 72 de 258171]" in out
