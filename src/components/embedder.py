import torch
from sentence_transformers import SentenceTransformer

from src.core.config import settings


def _supports_fp16(device: str) -> bool:
    """FP16 needs compute capability >= 7.0 (Volta). Pascal (6.x) lacks fast
    FP16 paths and newer PyTorch wheels skip its kernels — `.half()` raises
    'no kernel image' there. Use FP32 instead on Pascal and on CPU."""
    if device != "cuda":
        return False
    major, _ = torch.cuda.get_device_capability()
    return major >= 7


class Qwen3Embedder:
    def __init__(self, model_name: str | None = None, device: str | None = None):
        self.device = device or ("cuda" if torch.cuda.is_available() else "cpu")
        self.model_name = model_name or settings.qwen_embedding_model
        self.model = SentenceTransformer(
            self.model_name,
            device=self.device,
            trust_remote_code=True,
        )
        if _supports_fp16(self.device):
            self.model.half()  # FP16 -> ~1.2GB VRAM (Volta+)
        # Pascal/CPU: stay in FP32 (~2.4GB VRAM / system RAM)

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
