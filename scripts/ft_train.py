"""FASE C paso 2 — fine-tune Qwen3-Embedding-0.6B con pares coloquial→artículo.

MultipleNegativesRankingLoss (in-batch negatives). Congela embeddings + capas 0-19,
entrena capas 20-27 + norm (adaptación de registro en capas altas; ahorra memoria
de optimizador → entra en la GTX 1080 8GB). FP32 (Pascal no tiene fp16 rápido).

Uso: HF_HUB_OFFLINE=1 PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True \
       ./venv-gpu/bin/python -m scripts.ft_train
"""
import json
import torch
from sentence_transformers import SentenceTransformer, InputExample, losses
from torch.utils.data import DataLoader

import os
PAIRS = "data/eval/ft_pairs.jsonl"
OUTDIR = os.environ.get("FT_OUT", "models/qwen3-ft-coloquial")
FREEZE_BELOW = int(os.environ.get("FT_FREEZE_BELOW", 20))  # entrena capas >= esto
MAX_SEQ = int(os.environ.get("FT_MAX_SEQ", 192))
BATCH = int(os.environ.get("FT_BATCH", 8))
EPOCHS = int(os.environ.get("FT_EPOCHS", 2))
GRAD_CKPT = os.environ.get("FT_GRAD_CKPT", "0") == "1"


def main():
    pairs = [json.loads(l) for l in open(PAIRS) if l.strip()]
    # texto del artículo truncado (el query coloquial es corto); par positivo
    examples = [InputExample(texts=[p["q"], p["texto"][:1200]]) for p in pairs]
    print(f"pares: {len(examples)}")

    model = SentenceTransformer("Qwen/Qwen3-Embedding-0.6B", device="cuda",
                                trust_remote_code=True)
    model.max_seq_length = MAX_SEQ
    if GRAD_CKPT:
        try:
            model[0].auto_model.gradient_checkpointing_enable()
            print("gradient checkpointing ON")
        except Exception as e:
            print("grad ckpt no disponible:", e)

    # Congelar embeddings + capas bajas.
    frozen = trainable = 0
    for name, p in model.named_parameters():
        keep = ("embed_tokens" not in name)
        if "layers." in name:
            li = int(name.split("layers.")[1].split(".")[0])
            keep = li >= FREEZE_BELOW
        p.requires_grad = keep
        if keep:
            trainable += p.numel()
        else:
            frozen += p.numel()
    print(f"trainable={trainable/1e6:.0f}M  frozen={frozen/1e6:.0f}M")

    loader = DataLoader(examples, shuffle=True, batch_size=BATCH)
    loss = losses.MultipleNegativesRankingLoss(model)

    model.fit(
        train_objectives=[(loader, loss)],
        epochs=EPOCHS,
        warmup_steps=int(0.1 * len(loader)),
        optimizer_params={"lr": 2e-5},
        show_progress_bar=True,
        output_path=OUTDIR,
        use_amp=False,  # Pascal: sin fp16
    )
    print(f"LISTO -> {OUTDIR}")


if __name__ == "__main__":
    main()
