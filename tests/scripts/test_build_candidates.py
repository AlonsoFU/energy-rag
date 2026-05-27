"""Regression: build_candidates must let `define_termino` win the dedup.

Bug (2026-05-26): when the SAME article carried both a `cita` and a
`define_termino` edge and the `cita` row came first, the dedup kept the `cita`
row → the article was mislabeled origin="cita" and dropped from the trusted
Capa 1, so a worse candidate resolved. The definitional edge must always win.
"""
from datetime import date

from scripts.resolve_definition_sources import build_candidates


def _row(id_norma, articulo, tipo_relacion, fecha, norma_tipo="DECRETO",
         titulo="DECRETO 1 X", norma_numero=1):
    return {
        "id_norma": id_norma, "articulo": articulo,
        "tipo_relacion": tipo_relacion, "tipo": norma_tipo,
        "titulo": titulo, "norma_numero": norma_numero,
        "fecha_publicacion": fecha, "definicion": "una definición sustantiva",
        "texto": "Artículo: se entenderá por X: ...",
    }


def test_define_termino_wins_dedup_even_when_cita_comes_first():
    # Same article, cita listed BEFORE define_termino (the order that triggered
    # the bug, since the SQL does not order by tipo_relacion).
    rows = [
        _row("1160108", "2", "cita", date(2021, 5, 25)),
        _row("1160108", "2", "define_termino", date(2021, 5, 25)),
    ]
    cands = build_candidates(rows)
    assert len(cands) == 1
    assert cands[0]["origin"] == "curated"  # not "cita"


def test_curated_article_reaches_trusted_layer():
    # Two articles: one only cita, one with both edges. Both define_termino
    # articles must surface as curated.
    rows = [
        _row("1112591", "2", "define_termino", date(2017, 12, 12)),
        _row("1160108", "2", "cita", date(2021, 5, 25)),
        _row("1160108", "2", "define_termino", date(2021, 5, 25)),
        _row("1160108", "83", "cita", date(2021, 5, 25)),
    ]
    cands = build_candidates(rows)
    curated = sorted((c["id_norma"], c["articulo"]) for c in cands
                     if c["origin"] == "curated")
    assert curated == [("1112591", "2"), ("1160108", "2")]
