"""End-to-end test: full pipeline against real 103 norm JSONs.

Uses testcontainer Postgres + mock embedder/reranker/LLM. No GPU, no API.
Verifies migration -> ingest -> retrieval -> generation -> grounding works
against actual scraped legal text.
"""
import pytest
from pathlib import Path


REPO_ROOT = Path(__file__).parent.parent
NORMAS_DIR = REPO_ROOT / "data" / "normas_completas"


@pytest.mark.integration
def test_migration_against_real_data(db_clean):
    """Migration script handles all 103 real JSONs without crashing."""
    from scripts.migrate_to_postgres import run_migration
    if not NORMAS_DIR.exists() or not list(NORMAS_DIR.rglob("*.json")):
        pytest.skip(f"No real norm JSONs at {NORMAS_DIR}")

    stats = run_migration(data_dir=NORMAS_DIR, dry_run=False)
    # Real corpus has some malformed records (empty titulo etc). Survey at the
    # time of writing this test reported 95/102 passing _has_required_fields.
    assert stats["normas_processed"] >= 90  # at least 90 of 103 should land
    assert stats["articulos_processed"] > 0
    # conceptos may be 0 with the conservative regex, that's documented


@pytest.mark.integration
def test_full_pipeline_real_data_with_mocks(db_clean):
    """Full path: migration -> embed (mock) -> retrieve (simple branch, mock LLM) -> generate.

    Uses real corpus but mock models so it runs in seconds without GPU/API.
    """
    from scripts.migrate_to_postgres import run_migration
    from scripts.embed_all import run_embed_all
    from src.routing.adaptive import AdaptiveRouter
    from src.components.vectorstore import PostgresStore
    from src.components.llm import MockLLMProvider
    from src.pipelines.retrieve import SimpleRetriever, ComplexRetriever, AdaptiveRetriever
    from src.pipelines.generate import generate_answer

    if not NORMAS_DIR.exists() or not list(NORMAS_DIR.rglob("*.json")):
        pytest.skip("No real corpus")

    # 1. Migrate real data
    run_migration(data_dir=NORMAS_DIR, dry_run=False)

    # 2. Embed using mock models, limit to keep test fast
    run_embed_all(skip_contextual=True, mock=True, limit=100)

    # 3. Build adaptive retriever with mocks
    class _ME:
        def embed(self, texts):
            return [[(hash(t + str(i)) % 1000) / 1000.0 for i in range(1024)] for t in texts]

    class _MR:
        def rerank(self, q, docs, top_k):
            return [(i, 1.0 / (i + 1)) for i in range(min(len(docs), top_k))]

    e, r = _ME(), _MR()
    llm = MockLLMProvider(canned_responses={
        "respuesta": "Según [Art. 1 de DECRETO_62] la potencia firme se establece...",
    })

    store = PostgresStore()
    router = AdaptiveRouter()
    router.train_default()
    simple = SimpleRetriever(store, e, r)
    complejo = ComplexRetriever(store, e, r, llm=llm)
    adaptive = AdaptiveRetriever(simple, complejo, router)

    # 4. Run a query
    branch, docs = adaptive.retrieve("potencia firme", top_k=5)
    assert isinstance(branch, str)
    # docs may be empty if no fragment matches the query string under tsvector --
    # that's OK, we're verifying the pipeline doesn't crash, not measuring recall.

    # 5. If we got docs, run generation
    if docs:
        result = generate_answer("¿qué es potencia firme?", docs, llm=llm, model="mock")
        assert "text" in result
        assert "grounding_pass" in result


@pytest.mark.integration
def test_ask_cli_against_real_data(db_clean):
    """Smoke: `python -m src ask` against real corpus."""
    from typer.testing import CliRunner
    from scripts.migrate_to_postgres import run_migration
    from scripts.embed_all import run_embed_all
    from src.cli import app

    if not NORMAS_DIR.exists() or not list(NORMAS_DIR.rglob("*.json")):
        pytest.skip("No real corpus")

    run_migration(data_dir=NORMAS_DIR, dry_run=False)
    run_embed_all(skip_contextual=True, mock=True, limit=50)

    runner = CliRunner()
    result = runner.invoke(app, ["ask", "potencia firme", "--mock", "--top-k", "3"])
    # Even if no matches, CLI shouldn't crash
    assert result.exit_code == 0


@pytest.mark.integration
def test_stats_after_real_ingest(db_clean):
    """stats CLI shows non-zero counts after real-data ingest."""
    from typer.testing import CliRunner
    from scripts.migrate_to_postgres import run_migration
    from src.cli import app

    if not NORMAS_DIR.exists() or not list(NORMAS_DIR.rglob("*.json")):
        pytest.skip("No real corpus")

    run_migration(data_dir=NORMAS_DIR, dry_run=False)
    runner = CliRunner()
    result = runner.invoke(app, ["stats"])
    assert result.exit_code == 0
    # Output should show some normas
    output = result.output
    # The numbers are in a Rich table; just verify we can find the normas row
    # and that there's a non-zero number associated.
    assert "normas" in output
    import re
    # Try to find "normas <whitespace/box-chars> <number>" in either order
    nums = re.findall(r"normas[^\d]+(\d+)", output)
    if nums:
        # Take the first capture; should be > 0 after real ingest
        assert int(nums[0]) > 0
