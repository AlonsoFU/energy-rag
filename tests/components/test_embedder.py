import pytest


@pytest.mark.slow
def test_embedder_returns_correct_dim():
    from src.components.embedder import Qwen3Embedder

    emb = Qwen3Embedder()
    vecs = emb.embed(["hola mundo", "potencia firme"])
    assert len(vecs) == 2
    # Qwen3-Embedding-0.6B native output dim is 1024 (MRL-truncatable to [32, 1024]).
    # Phase 1 schema uses vector(768) -- see TODO in src/components/embedder.py.
    assert len(vecs[0]) == 1024


@pytest.mark.slow
def test_embedder_similar_texts_have_close_vectors():
    from src.components.embedder import Qwen3Embedder
    import numpy as np

    emb = Qwen3Embedder()
    a, b, c = emb.embed([
        "potencia firme",
        "potencia firme inicial",
        "compraventa de bienes raíces",
    ])
    sim_ab = float(np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b)))
    sim_ac = float(np.dot(a, c) / (np.linalg.norm(a) * np.linalg.norm(c)))
    assert sim_ab > sim_ac
