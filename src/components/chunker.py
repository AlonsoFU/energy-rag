from dataclasses import dataclass


@dataclass
class Chunk:
    chunk_index: int
    text: str
    token_count: int


class HierarchicalChunker:
    """Splits text into chunks with token-budget approximation (whitespace tokens)
    and overlap between consecutive chunks."""

    def __init__(self, target_tokens: int = 400, overlap_tokens: int = 50):
        self.target = target_tokens
        self.overlap = overlap_tokens

    def chunk(self, text: str) -> list[Chunk]:
        words = text.split()
        if len(words) <= self.target:
            return [Chunk(0, text, len(words))]

        chunks: list[Chunk] = []
        i = 0
        idx = 0
        step = self.target - self.overlap
        while i < len(words):
            chunk_words = words[i : i + self.target]
            chunks.append(Chunk(idx, " ".join(chunk_words), len(chunk_words)))
            idx += 1
            if i + self.target >= len(words):
                break
            i += step
        return chunks
