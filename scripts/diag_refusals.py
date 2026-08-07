"""Diagnostico de los RECHAZOS in_domain detectados por E3.

E3 mostro que 19 de las 26 fallas restantes NO son citas erradas: son RECHAZOS
(el sistema responde "no encuentro la norma") en queries que SI son del dominio.

Pregunta que decide el siguiente paso:
  gold EN el top-10 recuperado?  -> problema de GENERACION (no reconoce la definicion)
  gold FUERA del top-10?         -> problema de RETRIEVAL (D2 siglas, etc.)

Solo hace retrieval (sin generacion) -> barato, pocos minutos.

Uso: BGE_DEVICE=cuda PYTHONPATH=. venv/bin/python -m scripts.diag_refusals
"""
import json
from pathlib import Path
from src.components.embedder import Qwen3Embedder
from src.components.reranker import get_reranker
from src.components.vectorstore import PostgresStore
from src.components.llm import get_llm_provider
from src.pipelines.retrieve import SimpleRetriever, _normalize_art_g
from src.pipelines.grounding import _normalize_art
from src.core import config as cfg

E3 = Path("data/eval/results/e3_shotgun/result.json")


def main():
    rows = json.load(open(E3))["detail"]
    ref = [x for x in rows if not x.get("err") and not x["hit"] and x["refusal"]]
    other = [x for x in rows if not x.get("err") and not x["hit"] and not x["refusal"]]
    print(f"=== {len(ref)} rechazos + {len(other)} otras fallas ===", flush=True)

    e = Qwen3Embedder(); r = get_reranker(); store = PostgresStore(); llm = get_llm_provider()
    cfg.settings.embed_4b_dense = True; cfg.settings.embed_4b_dim = 1024; cfg.settings.alias_union = True
    pool = cfg.settings.retrieval_pool_depth
    retr = SimpleRetriever(store, e, r, top_bm25=pool, top_vector=pool, llm=llm)

    def check(items, label):
        print(f"\n### {label}", flush=True)
        en, fuera = [], []
        for x in items:
            gs = {(g.split("/", 1)[0], _normalize_art(g.split("/", 1)[1])) for g in x["gold"]}
            docs = retr.retrieve(x["query"], top_k=10)
            got = {(str(d["id_norma"]), _normalize_art(str(d["articulo_numero"]))) for d in docs}
            hit = bool(gs & got)
            rank = next((i for i, d in enumerate(docs)
                         if (str(d["id_norma"]), _normalize_art(str(d["articulo_numero"]))) in gs), None)
            (en if hit else fuera).append(x["query"])
            print(f"  {'EN pool rank=' + str(rank) if hit else 'FUERA del pool':18} | {x['query'][:50]}", flush=True)
        print(f"  --> {len(en)} con gold EN pool (fallo de GEN) | {len(fuera)} FUERA (fallo de RETRIEVAL)", flush=True)
        return en, fuera

    en_r, fuera_r = check(ref, "RECHAZOS")
    en_o, fuera_o = check(other, "OTRAS FALLAS")

    print(f"\n=== RESUMEN {len(ref) + len(other)} fallas ===", flush=True)
    print(f"  GEN      (gold estaba en el pool y no lo uso): {len(en_r) + len(en_o)}", flush=True)
    print(f"  RETRIEVAL(gold nunca llego al pool):           {len(fuera_r) + len(fuera_o)}", flush=True)


if __name__ == "__main__":
    main()
