"""Probe the 2 residual hangs (V.A.T.T., Usuario de Televía) with budget on.

Measures actual prompt size post-budget, then tests Ollama 3 ways:
(a) WITH schema (current production path) — should reveal if hang persists
(b) WITHOUT schema (plain) — isolates schema-induced deadlock
(c) WITHOUT schema, shorter prompt (top-3 docs) — controls for content
"""
import time
import requests
from src.core import config as cfg
from src.components.vectorstore import PostgresStore
from src.components.embedder import Qwen3Embedder
from src.components.reranker import Qwen3Reranker
from src.pipelines.retrieve import SimpleRetriever, ComplexRetriever, AdaptiveRetriever
from src.routing.adaptive import AdaptiveRouter
from src.pipelines.prompts import build_answer_prompt, get_answer_system, fit_docs_to_budget
from src.pipelines.grammar import extract_valid_citations, build_json_schema

QUERIES = ["qué es V.A.T.T.", "qué es Usuario de Televía"]
HOST = "http://localhost:11434"
MODEL = cfg.settings.llm_default.replace("ollama/", "")
TIMEOUT = 90


def main():
    store = PostgresStore()
    e, r = Qwen3Embedder(), Qwen3Reranker()
    router = AdaptiveRouter(); router.train_default()
    simple = SimpleRetriever(store, e, r)
    complejo = ComplexRetriever(store, e, r, llm=None)
    adaptive = AdaptiveRetriever(simple, complejo, router)

    for q in QUERIES:
        print(f"\n========== {q} ==========")
        _, docs = adaptive.retrieve(q, top_k=10)
        print(f"retrieved={len(docs)}")
        for variant_name, variant_docs in (
            ("budget=45000 (prod)", fit_docs_to_budget(docs, 45000)),
            ("top-3 only", docs[:3]),
        ):
            sys_p = get_answer_system()
            prompt = build_answer_prompt(q, variant_docs, char_budget=0)
            cits = extract_valid_citations(variant_docs)
            schema = build_json_schema(cits) if cits else None
            print(f"\n[{variant_name}] n_docs={len(variant_docs)} "
                  f"prompt_chars={len(prompt)} ~tokens={len(prompt)//3}")
            for label, fmt in (("WITH schema", schema), ("WITHOUT schema", None)):
                body = {
                    "model": MODEL, "prompt": prompt, "system": sys_p,
                    "think": False, "stream": False,
                    "options": {"num_ctx": 16384, "temperature": 0.0},
                }
                if fmt is not None:
                    body["format"] = fmt
                t0 = time.time()
                try:
                    rp = requests.post(f"{HOST}/api/generate", json=body,
                                       timeout=TIMEOUT)
                    d = rp.json()
                    dt = time.time() - t0
                    txt = d.get("response", "")
                    print(f"  [{label}] {dt:.1f}s "
                          f"prompt_eval={d.get('prompt_eval_count')} "
                          f"eval_count={d.get('eval_count')} "
                          f"resp_chars={len(txt)} "
                          f"first={txt[:80]!r}")
                except requests.exceptions.Timeout:
                    print(f"  [{label}] >>> HANG @ {TIMEOUT}s (0 tokens)")
                except Exception as ex:
                    print(f"  [{label}] error: {type(ex).__name__}: {ex}")


if __name__ == "__main__":
    main()
