"""Isolate the deterministic Ollama hang on 'qué es Acometida'.

Reproduces the exact generate-path prompt + JSON schema, then hits Ollama
/api/generate TWICE: (a) WITH format=schema (constrained decoding), (b)
WITHOUT format (plain generation). Same prompt, short timeout each. If only
(a) hangs → root cause is the constrained-decoding sampler on this doc set's
citation enum, not the model.
"""
import time
import requests

from src.core import config as cfg
from src.components.vectorstore import PostgresStore
from src.components.embedder import Qwen3Embedder
from src.components.reranker import Qwen3Reranker
from src.pipelines.retrieve import SimpleRetriever, ComplexRetriever, AdaptiveRetriever
from src.routing.adaptive import AdaptiveRouter
from src.pipelines.generate import build_answer_prompt, get_answer_system
from src.pipelines.grammar import extract_valid_citations, build_json_schema

QUERY = "qué es Acometida"
HOST = getattr(cfg.settings, "ollama_host", "http://localhost:11434")
MODEL = cfg.settings.llm_default.replace("ollama/", "")
TIMEOUT = 180


def main():
    store = PostgresStore()
    e, r = Qwen3Embedder(), Qwen3Reranker()
    router = AdaptiveRouter(); router.train_default()
    simple = SimpleRetriever(store, e, r)
    complejo = ComplexRetriever(store, e, r, llm=None)
    adaptive = AdaptiveRetriever(simple, complejo, router)

    branch, docs = adaptive.retrieve(QUERY, top_k=10)
    print(f"branch={branch} docs={len(docs)} model={MODEL}")

    prompt = build_answer_prompt(QUERY, docs)
    system = get_answer_system()
    cits = extract_valid_citations(docs)
    schema = build_json_schema(cits) if cits else None
    print(f"prompt_chars={len(prompt)} system_chars={len(system)} "
          f"n_valid_citations={len(cits) if cits else 0}")
    # rough token estimate (Spanish ~3.5 chars/token)
    print(f"~prompt_tokens≈{(len(prompt)+len(system))//4}")

    for label, fmt, nctx in (
        ("schema + num_ctx=8192", schema, 8192),
        ("schema + num_ctx=16384", schema, 16384),
        ("schema + num_ctx=32768", schema, 32768),
    ):
        body = {
            "model": MODEL, "prompt": prompt, "system": system,
            "think": False, "stream": False,
            "options": {"num_ctx": nctx, "temperature": 0.0},
        }
        if fmt is not None:
            body["format"] = fmt
        t0 = time.time()
        try:
            resp = requests.post(f"{HOST}/api/generate", json=body,
                                 timeout=TIMEOUT)
            d = resp.json()
            dt = time.time() - t0
            txt = d.get("response", "")
            print(f"\n[{label}] {dt:.1f}s  "
                  f"prompt_eval={d.get('prompt_eval_count')} "
                  f"eval_count={d.get('eval_count')} "
                  f"resp_len={len(txt)}")
            print(f"   response[:200]={txt[:200]!r}")
        except requests.exceptions.Timeout:
            print(f"\n[{label}] >>> HANG: timed out at {TIMEOUT}s "
                  f"(0 tokens, connection held)")
        except Exception as ex:
            print(f"\n[{label}] error: {type(ex).__name__}: {ex}")


if __name__ == "__main__":
    main()
