from src.extraction.definition_source import resolve_definition_source

NAME = "Coordinador"

def C(norma, art, rank, fecha, definicion):
    return {"id_norma": norma, "articulo": art, "rank": rank,
            "fecha": fecha, "definicion": definicion}

LABEL = "el Coordinador"
SUBSTANCE = ("órgano técnico independiente encargado de la coordinación de la "
             "operación del sistema eléctrico nacional, con patrimonio propio.")

def test_substantive_beats_label_same_rank():
    r = resolve_definition_source(NAME, [
        C("A", "2", 2, "2019-01-01", LABEL),
        C("B", "5", 2, "2018-01-01", SUBSTANCE),
    ])
    assert r["status"] == "resolved" and r["id_norma"] == "B"
    assert r["confianza"] == "alta" and r["criterio"] == "sustancia"

def test_higher_rank_substantive_wins():
    # LEY (rank 3) that is ALSO the most recent beats the older DECRETO: rank and
    # recency agree → safe to resolve by hierarchy. (A higher-rank-but-OLDER norm
    # would instead be unresolved — see test_rank_disagrees_with_recency_is_unresolved.)
    r = resolve_definition_source(NAME, [
        C("A", "2", 2, "2020-01-01", SUBSTANCE),
        C("B", "5", 3, "2021-01-01", SUBSTANCE + " Ley."),
    ])
    assert r["status"] == "resolved" and r["id_norma"] == "B"
    assert r["criterio"] == "jerarquia"

def test_rank_disagrees_with_recency_is_unresolved():
    # Substantive LEY (no date) vs substantive DECRETO (recent): B1 rule → ask.
    r = resolve_definition_source(NAME, [
        C("A", "2", 3, None, SUBSTANCE),
        C("B", "5", 2, "2021-01-01", SUBSTANCE),
    ])
    assert r["status"] == "unresolved"

def test_only_labels_is_unresolved():
    r = resolve_definition_source(NAME, [
        C("A", "2", 2, "2019-01-01", LABEL),
        C("B", "5", 2, "2018-01-01", "el Coordinador."),
    ])
    assert r["status"] == "unresolved" and r["reason"] == "no-substantive-candidate"

def test_single_substantive_resolves():
    r = resolve_definition_source(NAME, [C("A", "2", 2, "2019-01-01", SUBSTANCE)])
    assert r["status"] == "resolved" and r["id_norma"] == "A"
