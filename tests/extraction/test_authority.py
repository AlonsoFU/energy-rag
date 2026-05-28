from src.extraction.authority import select_authoritative


def C(norma, art, rank, fecha):
    return {"id_norma": norma, "articulo": art, "rank": rank, "fecha": fecha}


def test_higher_rank_wins_regardless_of_recency():
    # Refined 2026-05-28 ("jerarquía chilena"): a LEY (rank 3) strictly outranks a
    # DECRETO (rank 2). lex SUPERIOR governs across tiers; recency does not cross
    # tiers, so a newer DECRETO (2021) does NOT beat an older/undated LEY. Resolve
    # to the LEY. Real case: Sistema de Transmisión Nacional — LGSE art 74 (DFL,
    # 2006) beats DECRETO 37/2021 (Reglamento de Transmisión) that implements it.
    r = select_authoritative([C("1183783", "2", 3, None), C("1160108", "2", 2, "2021-05-25")])
    assert r["status"] == "resolved" and r["id_norma"] == "1183783"


def test_higher_rank_and_most_recent_resolves():
    # LEY is ALSO the most recent → rank and recency agree → resolve to the LEY.
    r = select_authoritative([C("1183783", "2", 3, "2022-01-01"), C("1160108", "2", 2, "2021-05-25")])
    assert r["status"] == "resolved" and r["id_norma"] == "1183783"


def test_same_rank_different_normas_is_conflict():
    # Refined 2026-05-26: same rank in two DIFFERENT normas → we cannot tell
    # lex-posterior (same context, newer wins) from a different ámbito (parallel
    # definitions) without ámbito detection → ask. Real case: Panel de Expertos
    # in DECRETO 10/2019 (Valorización) vs DECRETO 37/2021 (Transmisión).
    r = select_authoritative([C("1146553", "5", 2, "2019-02-01"), C("1160108", "2", 2, "2021-05-25")])
    assert r["status"] == "conflict"
    assert {c["id_norma"] for c in r["candidates"]} == {"1146553", "1160108"}


def test_same_rank_same_norma_recent_article_resolves():
    # Same norma, two articles, one strictly newer → genuine lex-posterior within
    # one context → resolve (not a different-ámbito ambiguity).
    r = select_authoritative([C("1160108", "2", 2, "2019-02-01"), C("1160108", "9", 2, "2021-05-25")])
    assert r["status"] == "resolved" and r["id_norma"] == "1160108" and r["articulo"] == "9"


def test_tie_rank_and_date_is_conflict():
    r = select_authoritative([C("A", "1", 3, "2020-01-01"), C("B", "2", 3, "2020-01-01")])
    assert r["status"] == "conflict"


def test_single_candidate():
    r = select_authoritative([C("A", "1", 2, "2020-01-01")])
    assert r["status"] == "resolved" and r["id_norma"] == "A"
