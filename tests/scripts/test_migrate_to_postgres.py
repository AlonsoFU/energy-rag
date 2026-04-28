"""Integration tests for ``scripts/migrate_to_postgres``.

Runs against the testcontainer Postgres set up by ``tests/conftest.py``.
"""
import json

import pytest

from scripts.migrate_to_postgres import run_migration
from src.storage.connection import with_connection


@pytest.mark.integration
def test_migrate_dry_run_empty_dir(db_clean, tmp_path):
    """Dry-run on an empty dir should report zero work."""
    stats = run_migration(data_dir=tmp_path, dry_run=True)
    assert stats["normas_processed"] == 0
    assert stats["articulos_processed"] == 0
    assert stats["conceptos_processed"] == 0


@pytest.mark.integration
def test_migrate_persists_normas_and_articulos(db_clean, tmp_path):
    """A small fixture norma must produce a Norma, ≥2 Articulos, ≥2 Conceptos."""
    decretos_dir = tmp_path / "decretos"
    decretos_dir.mkdir()
    fixture = {
        "id_norma": "TEST_1",
        "tipo": "DECRETO",
        "numero": "1",
        "titulo": "APRUEBA REGLAMENTO DE TEST",
        "fecha_publicacion": "2020-01-15",
        "organismo": "MINISTERIO DE TEST",
        "texto_completo": (
            "Artículo 1°.- Se establece el reglamento de prueba.\n"
            "Artículo 2°.- Para los efectos del presente reglamento:\n"
            "\n"
            "a) COMA: Costo de Operación, Mantenimiento y Administración del sistema.\n"
            "b) AVI: Anualidad del Valor de Inversión calculada anualmente.\n"
        ),
    }
    with open(decretos_dir / "decreto_test_1.json", "w", encoding="utf-8") as f:
        json.dump(fixture, f)

    stats = run_migration(data_dir=tmp_path, dry_run=False)

    assert stats["normas_processed"] == 1
    assert stats["articulos_processed"] >= 2
    assert stats["conceptos_processed"] >= 2

    with with_connection() as conn, conn.cursor() as cur:
        cur.execute("SELECT id_norma, clase FROM normas WHERE id_norma='TEST_1'")
        row = cur.fetchone()
        assert row is not None
        assert row[0] == "TEST_1"
        assert row[1] == "reglamento_base"

        cur.execute("SELECT count(*) FROM articulos WHERE id_norma='TEST_1'")
        assert cur.fetchone()[0] >= 2

        cur.execute("SELECT nombre FROM conceptos ORDER BY nombre")
        names = [r[0] for r in cur.fetchall()]
        assert "COMA" in names and "AVI" in names


@pytest.mark.integration
def test_migrate_skips_normas_with_missing_required_fields(db_clean, tmp_path):
    """Normas missing tipo/numero/titulo must be skipped (NOT NULL columns)."""
    leyes_dir = tmp_path / "leyes"
    leyes_dir.mkdir()
    bad = {
        "id_norma": "BROKEN",
        "tipo": "",
        "numero": "",
        "titulo": None,
        "fecha_publicacion": "",
        "organismo": "",
        "texto_completo": "",
    }
    with open(leyes_dir / "ley_broken.json", "w", encoding="utf-8") as f:
        json.dump(bad, f)

    stats = run_migration(data_dir=tmp_path, dry_run=False)

    assert stats["normas_processed"] == 0
    assert stats["normas_skipped"] == 1
    with with_connection() as conn, conn.cursor() as cur:
        cur.execute("SELECT count(*) FROM normas WHERE id_norma='BROKEN'")
        assert cur.fetchone()[0] == 0
