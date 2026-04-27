# TODO(reranker-api): verify Qwen3-Reranker-0.6B inference API matches AutoModelForSequenceClassification.
# Some Qwen rerankers are listwise / CausalLM-style requiring a custom prompt template
# and yes/no token probability extraction. The slow test will exercise the real model.
import torch
from transformers import AutoModelForSequenceClassification, AutoTokenizer

from src.core.config import settings


class Qwen3Reranker:
    def __init__(self, model_name: str | None = None, device: str | None = None):
        self.device = device or ("cuda" if torch.cuda.is_available() else "cpu")
        self.model_name = model_name or settings.qwen_reranker_model
        self.tokenizer = AutoTokenizer.from_pretrained(
            self.model_name, trust_remote_code=True
        )
        self.model = (
            AutoModelForSequenceClassification.from_pretrained(
                self.model_name,
                trust_remote_code=True,
                torch_dtype=torch.bfloat16 if self.device == "cuda" else torch.float32,
            )
            .to(self.device)
            .eval()
        )

    def rerank(
        self, query: str, docs: list[str], top_k: int
    ) -> list[tuple[int, float]]:
        """Returns list of (original_index, score) sorted by score desc, length=top_k."""
        if not docs:
            return []
        pairs = [[query, d] for d in docs]
        inputs = self.tokenizer(
            pairs,
            padding=True,
            truncation=True,
            return_tensors="pt",
            max_length=512,
        ).to(self.device)
        with torch.no_grad():
            scores = self.model(**inputs).logits.squeeze(-1).float().cpu().numpy()
        ranked = sorted(enumerate(scores), key=lambda x: x[1], reverse=True)
        return [(i, float(s)) for i, s in ranked[:top_k]]
