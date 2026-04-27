import torch
from sentence_transformers import SentenceTransformer

from src.core.config import settings


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
