from unittest.mock import MagicMock
from src.components.contextual import ContextualEnricher


def test_enricher_prefixes_context():
    fake_llm = MagicMock()
    fake_llm.generate.return_value = MagicMock(text="Este fragmento define COMA.", tokens_in=100, tokens_out=20)
    enricher = ContextualEnricher(llm=fake_llm)
    contextual = enricher.enrich(
        norma_titulo="D.S. N° 10",
        articulo_numero="2°",
        fragment_text="COMA: Costo de Operación...",
    )
    assert contextual.startswith("Este fragmento define COMA.")
    assert "COMA: Costo de Operación..." in contextual


def test_enricher_uses_default_mock_llm_when_none_provided():
    """When no LLM is passed, defaults to get_llm_provider() — should not crash."""
    enricher = ContextualEnricher()
    out = enricher.enrich(
        norma_titulo="D.S. 62",
        articulo_numero="5°",
        fragment_text="Texto del fragmento.",
    )
    assert out.endswith("Texto del fragmento.")
    assert len(out) > len("Texto del fragmento.")
