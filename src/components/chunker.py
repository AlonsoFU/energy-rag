import re
from dataclasses import dataclass


@dataclass
class Chunk:
    chunk_index: int
    text: str
    token_count: int


class HierarchicalChunker:
    """Splits text into chunks with token-budget approximation (whitespace tokens)
    and overlap between consecutive chunks. Legacy chunker — kept for backwards
    compatibility. Prefer SemanticChunker for new code."""

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


class SemanticChunker:
    """Sentence-boundary aware chunker for legal text.

    Rules (all deterministic Python, no LLM in runtime):
      1. Articles <=target words return as a single chunk (no slicing).
      2. Split by paragraphs (\\n\\n+) when present, else by sentence boundaries.
      3. Sentence boundary = period/exclamation/question followed by whitespace
         and capital letter — avoids splitting on abbreviations like "Sr." mid-text.
      4. Chunk arranca con oración o párrafo completo.
      5. Tamaño mínimo (default 100 palabras) — chunks cortos se mergean al anterior.
      6. Overlap por oraciones completas (default 2) en lugar de count fijo.
      7. Optional preamble: "[Artículo {numero} de {norma}] " prepended for self-
         contained retrieval.
    """

    SENT_SPLIT = re.compile(r"(?<=[.!?])\s+(?=[A-ZÁÉÍÓÚÑ])")
    PARAGRAPH = re.compile(r"\n\s*\n+")

    def __init__(
        self,
        target_tokens: int = 400,
        min_size: int = 100,
        overlap_units: int = 2,
    ):
        self.target = target_tokens
        self.min_size = min_size
        self.overlap_units = overlap_units

    def chunk(
        self,
        text: str,
        articulo_numero: str | None = None,
        id_norma: str | None = None,
    ) -> list[Chunk]:
        # Rule 1: short article → single chunk
        words = text.split()
        if len(words) <= self.target:
            preamble_text = self._with_preamble(text, articulo_numero, id_norma)
            return [Chunk(0, preamble_text, len(words))]

        # Rule 2+3: always split by sentence boundaries — paragraph-based split
        # was tried but fails when a single paragraph is much larger than target
        # (case real: a 1314-word paragraph would yield 1 unit instead of N).
        units = self.SENT_SPLIT.split(text)
        units = [u.strip() for u in units if u.strip()]

        # Edge case: if SENT_SPLIT yields a single huge unit (text has no
        # well-formed sentence terminators), fall back to whitespace splitting
        # so the rest of the algorithm still produces sane chunks.
        if len(units) == 1 and len(units[0].split()) > self.target * 2:
            words = units[0].split()
            step = self.target
            units = [" ".join(words[i:i + step]) for i in range(0, len(words), step)]

        chunks_text: list[str] = []
        current: list[str] = []
        current_words = 0

        for unit in units:
            n = len(unit.split())
            # Emit current chunk when over target AND has min size — Rule 5
            if current_words + n > self.target and current_words >= self.min_size:
                chunks_text.append(" ".join(current))
                # Rule 6: overlap by last N units
                overlap = current[-self.overlap_units:] if self.overlap_units > 0 else []
                current = overlap + [unit]
                current_words = sum(len(u.split()) for u in current)
            else:
                current.append(unit)
                current_words += n

        # Tail handling — merge tiny last chunk into previous
        if current:
            tail = " ".join(current)
            tail_words = sum(len(u.split()) for u in current)
            if chunks_text and tail_words < self.min_size:
                chunks_text[-1] = chunks_text[-1] + " " + tail
            else:
                chunks_text.append(tail)

        # Rule 7: prepend preamble to each chunk
        return [
            Chunk(
                idx,
                self._with_preamble(t, articulo_numero, id_norma),
                len(t.split()),
            )
            for idx, t in enumerate(chunks_text)
        ]

    @staticmethod
    def _with_preamble(text: str, numero: str | None, norma: str | None) -> str:
        text = text.strip()
        if numero and norma:
            return f"[Artículo {numero} de {norma}] {text}"
        return text
