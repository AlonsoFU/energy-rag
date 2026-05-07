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
        """Returns list of (original_index, score), length=top_k.

        IMPORTANT: this is currently an IDENTITY rerank — preserves the input
        order from RRF fusion. The Qwen3-Reranker checkpoint has its classifier
        head (`score.weight`) randomly initialized, so calling the model would
        return noise that destroys the upstream BM25+vector+RRF ranking. Eval
        on 2026-05-06 confirmed this: random rerank dropped recall@5 from 95.8%
        to 64.6%. Identity rerank is a no-op that at least doesn't regress.
        Wire proper yes/no token-probability scoring before re-enabling.
        """
        if not docs:
            return []
        n = min(len(docs), top_k)
        return [(i, 1.0 / (i + 1)) for i in range(n)]
