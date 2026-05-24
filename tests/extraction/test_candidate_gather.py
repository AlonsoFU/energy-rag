from src.extraction.candidate_gather import gather_candidates


def C(norma, art, extra=None):
    d = {"id_norma": norma, "articulo": art, "rank": 2, "fecha": "2020-01-01",
         "definicion": "texto"}
    if extra:
        d.update(extra)
    return d


def test_tags_origin():
    out = gather_candidates(curated=[C("A", "1")], retrieved=[C("B", "2")])
    by = {(c["id_norma"], c["articulo"]): c for c in out}
    assert by[("A", "1")]["origin"] == "curated"
    assert by[("B", "2")]["origin"] == "retrieved"


def test_dedup_prefers_curated():
    out = gather_candidates(curated=[C("A", "1")], retrieved=[C("A", "1"), C("B", "2")])
    assert len(out) == 2
    a = [c for c in out if c["id_norma"] == "A"][0]
    assert a["origin"] == "curated"


def test_empty_retrieved_returns_curated():
    out = gather_candidates(curated=[C("A", "1")], retrieved=[])
    assert len(out) == 1 and out[0]["origin"] == "curated"
