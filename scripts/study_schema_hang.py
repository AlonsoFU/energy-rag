"""Systematic study of which schema variant deadlocks Ollama on V.A.T.T.

Tests 6 variants on the same retrieved docs, isolating: enum format
heterogeneity vs enum size vs JSON-schema-vs-GBNF vs content.
"""
import re
import time
import requests
from src.core import config as cfg
from src.components.vectorstore import PostgresStore
from src.components.embedder import Qwen3Embedder
from src.components.reranker import Qwen3Reranker
from src.pipelines.retrieve import SimpleRetriever, ComplexRetriever, AdaptiveRetriever
from src.routing.adaptive import AdaptiveRouter
from src.pipelines.prompts import build_answer_prompt, get_answer_system
from src.pipelines.grammar import extract_valid_citations, build_json_schema, build_gbnf_grammar

QUERY = "qué es V.A.T.T."
HOST = "http://localhost:11434"
MODEL = cfg.settings.llm_default.replace("ollama/", "")
TIMEOUT = 60


def schema_from_cits(cits):
    enum_vals = [f"[Art. {a} de {n}]" for a, n in cits]
    return {
        "type": "object",
        "properties": {
            "answer": {"type": "string"},
            "citations": {"type": "array",
                          "items": {"type": "string", "enum": enum_vals}},
        },
        "required": ["answer", "citations"],
    }


def call_ollama(prompt, system, format_=None, grammar=None, label=""):
    body = {
        "model": MODEL, "prompt": prompt, "system": system,
        "think": False, "stream": False,
        "options": {"num_ctx": 16384, "temperature": 0.0},
    }
    if format_ is not None:
        body["format"] = format_
    if grammar is not None:
        body["options"]["grammar"] = grammar
    t0 = time.time()
    try:
        rp = requests.post(f"{HOST}/api/generate", json=body, timeout=TIMEOUT)
        d = rp.json()
        dt = time.time() - t0
        txt = d.get("response", "")
        status = "OK" if txt.strip() else "EMPTY"
        print(f"  [{label}] {status} {dt:.1f}s  "
              f"prompt_eval={d.get('prompt_eval_count')} "
              f"eval_count={d.get('eval_count')} "
              f"resp[:90]={txt[:90]!r}")
    except requests.exceptions.Timeout:
        print(f"  [{label}] >>> HANG @ {TIMEOUT}s")
    except Exception as ex:
        print(f"  [{label}] ERR: {type(ex).__name__}: {ex}")


def main():
    store = PostgresStore()
    e, r = Qwen3Embedder(), Qwen3Reranker()
    router = AdaptiveRouter(); router.train_default()
    simple = SimpleRetriever(store, e, r)
    complejo = ComplexRetriever(store, e, r, llm=None)
    adaptive = AdaptiveRetriever(simple, complejo, router)
    _, docs = adaptive.retrieve(QUERY, top_k=10)
    prompt = build_answer_prompt(QUERY, docs, char_budget=0)
    system = get_answer_system()
    all_cits = extract_valid_citations(docs)
    digit_re = re.compile(r"^\d")
    digit_cits = [c for c in all_cits if digit_re.match(c[0])]
    word_cits = [c for c in all_cits if not digit_re.match(c[0])]
    mixed_2 = [digit_cits[0], word_cits[0]] if digit_cits and word_cits else all_cits[:2]

    print(f"# docs={len(docs)}  prompt_chars={len(prompt)}")
    print(f"# all citations ({len(all_cits)}): {all_cits}")
    print(f"# digit-only ({len(digit_cits)}): {digit_cits}")
    print(f"# word-only ({len(word_cits)}): {word_cits}")
    print(f"# mixed-2: {mixed_2}")
    print()

    print("[A] full JSON schema, 10 mixed (PRODUCTION)")
    call_ollama(prompt, system, format_=schema_from_cits(all_cits), label="A")
    print("[B] JSON schema, only DIGIT articles")
    call_ollama(prompt, system, format_=schema_from_cits(digit_cits), label="B")
    print("[C] JSON schema, 2 entries (1 digit + 1 word)")
    call_ollama(prompt, system, format_=schema_from_cits(mixed_2), label="C")
    print("[F] JSON schema, only WORD articles")
    call_ollama(prompt, system, format_=schema_from_cits(word_cits), label="F")
    print("[D] GBNF grammar (Ollama native, all 10)")
    call_ollama(prompt, system, grammar=build_gbnf_grammar(all_cits), label="D")
    print("[E] no schema (control)")
    call_ollama(prompt, system, label="E")


if __name__ == "__main__":
    main()
