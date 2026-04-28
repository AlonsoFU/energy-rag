from unittest.mock import MagicMock

from src.pipelines.expansion import hyde, multi_query, step_back


def test_hyde_returns_hypothetical_doc():
    fake = MagicMock()
    fake.generate.return_value = MagicMock(
        text="La potencia firme es la capacidad...", tokens_in=10, tokens_out=20
    )
    out = hyde("¿qué es potencia firme?", llm=fake)
    assert "potencia firme" in out.lower()


def test_multi_query_returns_3_variants():
    fake = MagicMock()
    fake.generate.return_value = MagicMock(
        text="¿qué es COMA?\n¿cómo se calcula COMA?\n¿quién regula COMA?",
        tokens_in=10,
        tokens_out=20,
    )
    out = multi_query("¿qué es COMA?", llm=fake)
    assert len(out) == 3


def test_step_back_returns_general_question():
    fake = MagicMock()
    fake.generate.return_value = MagicMock(
        text="¿Qué es la regulación de transferencias eléctricas?",
        tokens_in=10,
        tokens_out=20,
    )
    out = step_back("Art. 5 del D.S. 62", llm=fake)
    assert "regulación" in out.lower()
