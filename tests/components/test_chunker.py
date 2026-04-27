from src.components.chunker import HierarchicalChunker


def test_chunker_short_text_returns_one_chunk():
    c = HierarchicalChunker(target_tokens=400, overlap_tokens=50)
    chunks = c.chunk("Texto corto")
    assert len(chunks) == 1
    assert chunks[0].chunk_index == 0
    assert chunks[0].text == "Texto corto"


def test_chunker_long_text_splits_with_overlap():
    c = HierarchicalChunker(target_tokens=10, overlap_tokens=2)
    text = " ".join([f"palabra{i}" for i in range(50)])  # 50 tokens
    chunks = c.chunk(text)
    assert len(chunks) > 1
    # Verify overlap: end of chunk i should be start of chunk i+1
    for a, b in zip(chunks, chunks[1:]):
        a_words = a.text.split()
        b_words = b.text.split()
        assert a_words[-2:] == b_words[:2]


def test_chunk_indices_are_sequential():
    c = HierarchicalChunker(target_tokens=10, overlap_tokens=2)
    text = " ".join([f"x{i}" for i in range(100)])
    chunks = c.chunk(text)
    for i, ch in enumerate(chunks):
        assert ch.chunk_index == i
