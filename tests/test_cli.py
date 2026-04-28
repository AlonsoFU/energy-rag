import pytest
from typer.testing import CliRunner
from src.cli import app

runner = CliRunner()


@pytest.mark.integration
def test_stats_runs_against_empty_db(db_clean):
    """Smoke: stats command outputs counts (zero rows) without crashing."""
    result = runner.invoke(app, ["stats"])
    assert result.exit_code == 0
    assert "normas" in result.output


@pytest.mark.integration
def test_ask_end_to_end_with_mock(db_clean):
    """Full ask path: ingest 1 articulo+fragmento, ask a question, get grounded answer."""
    from src.components.vectorstore import PostgresStore
    from src.core.models import Norma, Articulo, Fragmento
    s = PostgresStore()
    s.upsert_norma(Norma(id_norma="DECRETO_62", tipo="DECRETO", numero="62", titulo="Reglamento Transferencias"))
    aid = s.upsert_articulo(Articulo(id_norma="DECRETO_62", numero="1",
                                     texto="Se entenderá por potencia firme la capacidad..."))
    s.upsert_fragmento(Fragmento(
        articulo_id=aid, chunk_index=0,
        text="potencia firme capacidad",
        contextual_text="potencia firme capacidad de generación",
        embedding=[0.5]*1024,
    ))
    result = runner.invoke(app, ["ask", "potencia firme", "--mock", "--top-k", "3"])
    assert result.exit_code == 0
    assert "Respuesta" in result.output


def test_update_stub_runs():
    """update --dry-run is a stub but should exit cleanly."""
    result = runner.invoke(app, ["update", "--dry-run"])
    assert result.exit_code == 0


def test_help_works():
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "ask" in result.output
    assert "ingest" in result.output
    assert "stats" in result.output


def test_eval_command_help_listed():
    result = runner.invoke(app, ["--help"])
    assert "eval" in result.output
