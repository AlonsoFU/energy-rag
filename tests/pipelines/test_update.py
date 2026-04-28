import pytest
from src.pipelines.update import diff_against_db, run_update


@pytest.mark.integration
def test_diff_detects_new(db_clean):
    from src.storage.connection import with_connection
    with with_connection() as conn, conn.cursor() as cur:
        cur.execute("INSERT INTO descargas_estado (id_norma, estado, bcn_hash) VALUES ('A','downloaded','h1')")
        conn.commit()
    diff = diff_against_db([
        {"id_norma": "A", "hash": "h1"},
        {"id_norma": "B", "hash": "h2"},
    ])
    assert diff["nuevas"] == ["B"]
    assert diff["outdated"] == []


@pytest.mark.integration
def test_diff_detects_outdated(db_clean):
    from src.storage.connection import with_connection
    with with_connection() as conn, conn.cursor() as cur:
        cur.execute("INSERT INTO descargas_estado (id_norma, estado, bcn_hash) VALUES ('A','downloaded','h1')")
        conn.commit()
    diff = diff_against_db([{"id_norma": "A", "hash": "h2_changed"}])
    assert diff["outdated"] == ["A"]


@pytest.mark.integration
def test_diff_detects_desaparecidas(db_clean):
    from src.storage.connection import with_connection
    with with_connection() as conn, conn.cursor() as cur:
        cur.execute("INSERT INTO descargas_estado (id_norma, estado, bcn_hash) VALUES ('A','downloaded','h1')")
        conn.commit()
    diff = diff_against_db([])
    assert "A" in diff["desaparecidas"]


def test_run_update_dry_run_does_not_crash():
    """run_update with dry_run uses an injectable bcn_index."""
    diff = run_update(dry_run=True, bcn_index=[])
    assert isinstance(diff, dict)
