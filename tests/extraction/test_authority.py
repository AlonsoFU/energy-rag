from src.extraction.authority import select_authoritative


def C(norma, art, rank, fecha):
    return {"id_norma": norma, "articulo": art, "rank": rank, "fecha": fecha}


def test_higher_rank_but_older_is_conflict():
    # LEY 1183783 (no date, possibly different context) vs DECRETO 1160108 (2021):
    # rank winner != recency winner → not sure → ask (refined rule).
    r = select_authoritative([C("1183783", "2", 3, None), C("1160108", "2", 2, "2021-05-25")])
    assert r["status"] == "conflict"
    assert {c["id_norma"] for c in r["candidates"]} == {"1183783", "1160108"}


def test_higher_rank_and_most_recent_resolves():
    # LEY is ALSO the most recent → rank and recency agree → resolve to the LEY.
    r = select_authoritative([C("1183783", "2", 3, "2022-01-01"), C("1160108", "2", 2, "2021-05-25")])
    assert r["status"] == "resolved" and r["id_norma"] == "1183783"


def test_same_rank_recent_wins():
    r = select_authoritative([C("1146553", "5", 2, "2019-02-01"), C("1160108", "2", 2, "2021-05-25")])
    assert r["status"] == "resolved" and r["id_norma"] == "1160108"


def test_tie_rank_and_date_is_conflict():
    r = select_authoritative([C("A", "1", 3, "2020-01-01"), C("B", "2", 3, "2020-01-01")])
    assert r["status"] == "conflict"


def test_single_candidate():
    r = select_authoritative([C("A", "1", 2, "2020-01-01")])
    assert r["status"] == "resolved" and r["id_norma"] == "A"
