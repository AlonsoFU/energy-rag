"""Edge cases in chunking observed with legal text."""
from src.components.chunker import HierarchicalChunker


def test_chunk_handles_excessive_whitespace():
    """Legal text often has multiple spaces, newlines, non-breaking spaces."""
    chunker = HierarchicalChunker(target_tokens=10, overlap_tokens=2)
    text = "palabra\n\n\nuno   dos\xa0\xa0tres   " * 5  # mixed whitespace
    chunks = chunker.chunk(text)
    assert len(chunks) >= 1
    # No empty chunks
    for c in chunks:
        assert c.text.strip()


def test_chunk_empty_text():
    chunker = HierarchicalChunker(target_tokens=10, overlap_tokens=2)
    chunks = chunker.chunk("")
    # Empty input -> either no chunks OR one empty chunk; both acceptable
    assert isinstance(chunks, list)


def test_chunk_single_word_below_target():
    chunker = HierarchicalChunker(target_tokens=10, overlap_tokens=2)
    chunks = chunker.chunk("hola")
    assert len(chunks) == 1
    assert chunks[0].text == "hola"


def test_chunk_overlap_zero():
    """overlap_tokens=0 still works (no overlap, just sequential split)."""
    chunker = HierarchicalChunker(target_tokens=5, overlap_tokens=0)
    text = " ".join([f"w{i}" for i in range(20)])
    chunks = chunker.chunk(text)
    assert len(chunks) >= 4
    # No overlap -> consecutive chunks should not share words
    for a, b in zip(chunks, chunks[1:]):
        assert set(a.text.split()) & set(b.text.split()) == set() or len(a.text.split()) < 5
