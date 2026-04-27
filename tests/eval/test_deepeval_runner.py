from unittest.mock import MagicMock


def test_deepeval_runs_on_minimal_set(tmp_path):
    """Smoke: runner accepts queries+expected and returns metrics dict."""
    from src.eval.deepeval_runner import run_deepeval
    eval_file = tmp_path / "eval.jsonl"
    eval_file.write_text(
        '{"query": "test", "expected_norma": "X", "expected_articulo": "1"}\n'
    )
    fake_retriever = MagicMock()
    fake_retriever.retrieve.return_value = ("simple", [
        {"id_norma": "X", "articulo_numero": "1", "articulo_text": "..."}
    ])
    metrics = run_deepeval(eval_file=eval_file, retriever=fake_retriever)
    assert metrics["recall_at_5"] == 1.0
    assert metrics["n_queries"] == 1


def test_deepeval_recall_zero_on_no_match(tmp_path):
    from src.eval.deepeval_runner import run_deepeval
    eval_file = tmp_path / "eval.jsonl"
    eval_file.write_text('{"query": "test", "expected_norma": "X", "expected_articulo": "1"}\n')
    fake = MagicMock()
    fake.retrieve.return_value = ("simple", [
        {"id_norma": "OTHER", "articulo_numero": "99", "articulo_text": "..."}
    ])
    metrics = run_deepeval(eval_file=eval_file, retriever=fake)
    assert metrics["recall_at_5"] == 0.0


def test_deepeval_articulo_none_means_norma_only(tmp_path):
    """When expected_articulo is null, just having the right norma counts as hit."""
    from src.eval.deepeval_runner import run_deepeval
    eval_file = tmp_path / "eval.jsonl"
    eval_file.write_text('{"query": "test", "expected_norma": "X", "expected_articulo": null}\n')
    fake = MagicMock()
    fake.retrieve.return_value = ("simple", [
        {"id_norma": "X", "articulo_numero": "99", "articulo_text": "..."}
    ])
    metrics = run_deepeval(eval_file=eval_file, retriever=fake)
    assert metrics["recall_at_5"] == 1.0
