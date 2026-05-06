# TODO(reranker-api): verify Qwen3-Reranker-0.6B inference API matches AutoModelForSequenceClassification.
# Some Qwen rerankers are listwise / CausalLM-style requiring a custom prompt template
# and yes/no token probability extraction. The slow test will exercise the real model.
import torch
from transformers import AutoModelForSequenceClassification, AutoTokenizer

from src.core.config import settings


class Qwen3Reranker:
    def __init__(self, model_name: str | None = None, device: str | None = None):
        # Resolve device with same precedence as Qwen3Embedder.
        if device is None:
            cfg = (settings.reranker_device or "auto").lower()
            if cfg == "auto":
                device = "cuda" if torch.cuda.is_available() else "cpu"
            else:
                device = cfg
        self.device = device
        self.model_name = model_name or settings.qwen_reranker_model
        self.tokenizer = AutoTokenizer.from_pretrained(
            self.model_name, trust_remote_code=True
        )
        # Qwen3-Reranker has no pad_token; needed when batching pairs in rerank().
        if self.tokenizer.pad_token is None:
            self.tokenizer.pad_token = self.tokenizer.eos_token
        self.model = (
            AutoModelForSequenceClassification.from_pretrained(
                self.model_name,
                trust_remote_code=True,
                torch_dtype=torch.bfloat16 if self.device == "cuda" else torch.float32,
            )
            .to(self.device)
            .eval()
        )
        # transformers 5.x rejects batched forward when model.config.pad_token_id
        # is unset — sync it to the tokenizer's pad token after both are loaded.
        if self.model.config.pad_token_id is None:
            self.model.config.pad_token_id = self.tokenizer.pad_token_id

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
            logits = self.model(**inputs).logits.float().cpu()
        # Qwen3-Reranker via AutoModelForSequenceClassification returns (N, 2)
        # logits with the classifier head randomly initialized (`score.weight`
        # missing from checkpoint). Use the positive-class margin as score —
        # weights are random, so this rerank step is effectively a no-op until
        # we wire the proper yes/no token-probability API (see TODO at top).
        if logits.dim() == 2 and logits.shape[-1] == 2:
            scores = (logits[:, 1] - logits[:, 0]).numpy()
        else:
            scores = logits.squeeze(-1).numpy()
        ranked = sorted(enumerate(scores.tolist()), key=lambda x: x[1], reverse=True)
        return [(i, float(s)) for i, s in ranked[:top_k]]
