"""Quick prompt iteration harness — call Ollama with the actual prompt
the pipeline would build, see raw response, check grounding."""
import sys
sys.path.insert(0, ".")

from src.components.vectorstore import PostgresStore
from src.components.embedder import Qwen3Embedder  # only needed if running real pipeline
from src.routing.adaptive import AdaptiveRouter
from src.pipelines.retrieve import SimpleRetriever
from src.pipelines.prompts import build_answer_prompt, get_answer_system
from src.pipelines.grounding import verify_citations, extract_citations
import requests, json


class _MockEmbedder:
    def embed(self, texts):
        return [[(hash(t + str(i)) % 1000) / 1000.0 for i in range(1024)] for t in texts]


class _MockReranker:
    def rerank(self, q, docs, top_k):
        return [(i, 1.0/(i+1)) for i in range(min(len(docs), top_k))]


def call_ollama(model: str, system: str, user: str) -> str:
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "stream": False,
        "options": {"temperature": 0.0},
    }
    r = requests.post("http://localhost:11434/api/chat", json=payload, timeout=180)
    r.raise_for_status()
    return r.json()["message"]["content"]


def run_query(query: str, model: str = "qwen2.5:7b", top_k: int = 3, show_prompt: bool = False):
    store = PostgresStore()
    retriever = SimpleRetriever(store, _MockEmbedder(), _MockReranker())
    docs = retriever.retrieve(query, top_k=top_k)

    system = get_answer_system()
    user = build_answer_prompt(query, docs)

    if show_prompt:
        print("=== SYSTEM ===")
        print(system)
        print("=== USER ===")
        print(user[:1500])
        print("..." if len(user) > 1500 else "")
        print("=" * 60)

    response = call_ollama(model, system, user)

    print("=== RESPONSE ===")
    print(response)
    print("=" * 60)

    cits = extract_citations(response)
    valid = {(d["id_norma"], str(d["articulo_numero"]).rstrip("°")) for d in docs}
    print(f"=== CITATIONS FOUND ===  {len(cits)}")
    for c in cits:
        ok = c in valid
        print(f"  {'✓' if ok else '✗'}  {c}")
    print(f"=== VALID CITATIONS POOL ===  {len(valid)}")
    for v in valid:
        print(f"  - {v}")
    print(f"=== GROUNDING PASS: {verify_citations(response, docs)} ===")


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("query")
    ap.add_argument("--model", default="qwen2.5:7b")
    ap.add_argument("--top-k", type=int, default=3)
    ap.add_argument("--show-prompt", action="store_true")
    args = ap.parse_args()
    run_query(args.query, args.model, args.top_k, args.show_prompt)
