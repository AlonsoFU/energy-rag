"""Test (solo-lectura) de HyDE / query-expansion para recall de paráfrasis.

Hipótesis (Paso 2 real): el embedding de una query parafraseada no matchea el
del artículo (gold∈pool = 7/15 @20, baseline). Si generamos una RESPUESTA
HIPOTÉTICA con el LLM y recuperamos con SU embedding, puenteamos
paráfrasis→artículo. Legal-safe: solo cambia lo que se RECUPERA; la cita final
sigue siendo exacta.

Mide gold∈pool@20 para 3 variantes: query sola (baseline), hyde sola,
query+hyde. NO genera respuesta final, no cita, no modifica nada.
Genera el HyDE con el LLM primero; el embedder/reranker corren en CPU para
evitar contención de VRAM con el 9b de Ollama.
"""
import json
from pathlib import Path

from src.components.llm import get_llm_provider
from src.components.embedder import Qwen3Embedder
from src.components.reranker import Qwen3Reranker
from src.components.vectorstore import PostgresStore
from src.pipelines.retrieve import SimpleRetriever, ComplexRetriever, AdaptiveRetriever
from src.routing.adaptive import AdaptiveRouter
from src.core import config as cfg
from src.pipelines.grounding import _normalize_art

EVAL = Path("data/eval/queries_independent.jsonl")
TOP_K = 20
HYDE_MODEL = "ollama/qwen3.5:9b"

HYDE_SYSTEM = (
    "Eres un experto en derecho eléctrico chileno. Te doy una pregunta. "
    "Redacta UN párrafo breve (2-4 frases) como si fuera el texto de la ley o "
    "reglamento que responde esa pregunta, usando la terminología técnica/legal "
    "exacta que aparecería en la norma. No cites artículos ni inventes números; "
    "solo redacta el contenido normativo probable. Responde solo el párrafo."
)


def _in_pool(docs, norma, art):
    ta = _normalize_art(str(art))
    return any(str(d.get("id_norma")) == str(norma)
              and _normalize_art(str(d.get("articulo_numero"))) == ta for d in docs)


HYDE_CACHE = Path("/tmp/hyde_indep_complex.json")


def main():
    import sys
    rows = [json.loads(l) for l in EVAL.read_text().splitlines() if l.strip()]
    rows = [r for r in rows if r["category"] == "indep_complex"]

    # Fase 1 (--gen): generar HyDE con el LLM (GPU vía Ollama), cachear, salir.
    if "--gen" in sys.argv:
        llm = get_llm_provider()
        hyde = {}
        for q in rows:
            resp = llm.generate(q["query"], model=HYDE_MODEL, system=HYDE_SYSTEM,
                                temperature=0.0, max_tokens=200)
            hyde[q["query"]] = (resp.text or "").strip()
        HYDE_CACHE.write_text(json.dumps(hyde, ensure_ascii=False, indent=2))
        print(f"== HyDE generado y cacheado en {HYDE_CACHE} ==")
        return

    # Fase 2: retrieval en GPU con SimpleRetriever (BM25+vector+rerank, SIN LLM
    # → mide recall puro y evita reload del 9b por el ComplexRetriever).
    hyde = json.loads(HYDE_CACHE.read_text())
    pool = cfg.settings.retrieval_pool_depth
    e = Qwen3Embedder()
    r = Qwen3Reranker()
    store = PostgresStore()
    simple = SimpleRetriever(store, e, r, top_bm25=pool, top_vector=pool)

    base_hit = hyde_hit = comb_hit = 0
    for q in rows:
        query = q["query"]
        gold = (str(q["expected_norma"]), str(q["expected_articulo"]))
        h = hyde[query]
        d_base = simple.retrieve(query, top_k=TOP_K)
        d_hyde = simple.retrieve(h, top_k=TOP_K)
        d_comb = simple.retrieve(query + "\n" + h, top_k=TOP_K)
        b = _in_pool(d_base, *gold); hy = _in_pool(d_hyde, *gold); co = _in_pool(d_comb, *gold)
        base_hit += b; hyde_hit += hy; comb_hit += co
        flag = "↑" if (hy or co) and not b else (" " if b else "·")
        print(f"[{flag}] gold={gold[0]}/{gold[1]}  base={'Y' if b else 'N'} hyde={'Y' if hy else 'N'} comb={'Y' if co else 'N'}")
        print(f"    {query[:75]}")

    n = len(rows)
    print(f"\n== gold ∈ pool@{TOP_K} ==")
    print(f"baseline (query sola): {base_hit}/{n}")
    print(f"HyDE sola            : {hyde_hit}/{n}")
    print(f"query + HyDE         : {comb_hit}/{n}")


if __name__ == "__main__":
    main()
