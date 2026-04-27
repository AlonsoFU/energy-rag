import torch
from sentence_transformers import SentenceTransformer

from src.core.config import settings

# TODO(schema-mismatch): Qwen3-Embedding-0.6B outputs 1024-dim vectors by default,
# but Phase 1 schema declares `vector(768)`. The model supports Matryoshka
# Representation Learning (MRL) with custom dims in [32, 1024], so we can either:
#   (a) truncate output to 768 dims via MRL (set `truncate_dim=768` on the
#       SentenceTransformer or slice + renormalize after encode), or
#   (b) migrate the schema to `vector(1024)`.
# Decide before persisting any embeddings to Postgres.


class Qwen3Embedder:
    def __init__(self, model_name: str | None = None, device: str | None = None):
        self.device = device or ("cuda" if torch.cuda.is_available() else "cpu")
        self.model_name = model_name or settings.qwen_embedding_model
        self.model = SentenceTransformer(
            self.model_name,
            device=self.device,
            trust_remote_code=True,
        )
        if self.device == "cuda":
            self.model.half()  # FP16 -> ~1.2GB VRAM

    def embed(self, texts: list[str], batch_size: int = 32) -> list[list[float]]:
        with torch.no_grad():
            vecs = self.model.encode(
                texts,
                batch_size=batch_size,
                normalize_embeddings=True,
                show_progress_bar=False,
                convert_to_numpy=True,
            )
        return vecs.tolist()
