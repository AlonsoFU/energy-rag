"""¿Los fallos son de RETRIEVAL o de GENERACION? — el diagnostico que decide donde trabajar.

Motivo: con la config adoptada (exp #63) el set operativo queda en 64/114 `cita_ok` y 45/114
`cita_limpia`, y el grueso del fallo esta en UN frente: `cx_coloquial`, 50 de las 114 queries,
con 11/50 usables. Antes de tocar nada hay que saber en cual de las dos mitades del sistema
esta el problema, porque las soluciones no se parecen en nada:

    gold NO esta en el pool    -> es RETRIEVAL. Generar mejor no lo puede arreglar.
    gold SI esta y no lo cito  -> es GENERACION. Mas recall no lo puede arreglar.

Se cruza el pool recuperado (aca) con lo que el modelo respondio (guardado en el result.json
del pareado), asi que NO hay que volver a generar: solo retrieval, ~2 s por query en vez de
~200 s. La GPU se usa para el embedder y el reranker nada mas.

    env PYTHONPATH=. SET=data/eval/queries_operativas_v1.jsonl \
        RES=data/eval/results/def_dev/result.json venv/bin/python -m scripts.diag_donde_falla
"""
import collections, json, os
from pathlib import Path
from src.components.embedder import Qwen3Embedder
from src.components.reranker import get_reranker
from src.components.vectorstore import PostgresStore
from src.components.llm import get_llm_provider
from src.pipelines.retrieve import SimpleRetriever
from src.pipelines.grounding import _normalize_art, extract_citations
from src.core import config as cfg

SET = Path(os.environ.get("SET", "data/eval/queries_operativas_v1.jsonl"))
RES = Path(os.environ.get("RES", "data/eval/results/def_dev/result.json"))
TOPK = int(os.environ.get("TOPK", "10"))
# POOL = cuantos candidatos junta BM25/vector ANTES del rerank (config.retrieval_pool_depth).
# TOPK recorta DESPUES del rerank. Son dos preguntas distintas y hay que poder moverlas por
# separado: con POOL=50/TOPK=10 vs POOL=50/TOPK=50 se midio cuanto hunde el rerank (8 queries);
# subir POOL dice si el gold es ALCANZABLE por los generadores de candidatos o directamente no
# lo es a ninguna profundidad.
POOL = int(os.environ.get("POOL", "0"))
# El archivo lleva el TOPK en el nombre: la corrida con TOPK=50 no debe pisar la de 10, la
# comparacion entre las dos ES el resultado.
OUT = Path("data/eval/results/donde_falla_top%s_pool%s_rr%s.json" % (
    TOPK, POOL or 50, os.environ.get("TOP_RERANK_OVERRIDE", "10")))


def golds(q):
    out = {(str(q["expected_norma"]), _normalize_art(str(q["expected_articulo"])))}
    for g in q.get("also_gold") or []:
        n, a = str(g).split("/", 1); out.add((n, _normalize_art(a)))
    return out


def rank_gold(docs, gs):
    """Posicion del primer doc que ES un gold. None si el gold no vino en el pool.

    Las claves son `id_norma` y `articulo_numero` -- las mismas que usa retrieve.py:613 para
    deduplicar. Primero escribi `numero`/`articulo`, que NO existen en el dict: con eso ningun
    doc habria matcheado nunca y el diagnostico habria dicho "100 % retrieval" con total
    aplomo. De ahi el guardia de `main()`.
    """
    for i, d in enumerate(docs):
        par = (str(d.get("id_norma") or ""),
               _normalize_art(str(d.get("articulo_numero") or "")))
        if par in gs:
            return i
    return None


def main():
    rows = [json.loads(l) for l in SET.read_text().splitlines() if l.strip()]
    rows = [q for q in rows if not q.get("unanswerable")]
    # el texto que YA genero el pareado: no se vuelve a generar nada
    prev = {}
    if RES.exists():
        for c in json.load(open(RES))["detail"]:
            if c.get("on"):
                prev[c["query"]] = c["on"]

    llm = get_llm_provider()
    if POOL:
        cfg.settings.retrieval_pool_depth = POOL
    # EL cuello: el reranker deja pasar `top_rerank=10` fijo (retrieve.py:457) y TOPK recorta
    # DESPUES. Subir TOPK sin esto no puede traer un solo gold mas -- asi se perdieron las
    # corridas v16/v17.
    _tro = int(os.environ.get("TOP_RERANK_OVERRIDE", "0"))
    if _tro:
        cfg.settings.top_rerank_override = _tro
    cfg.settings.embed_4b_dense = True; cfg.settings.embed_4b_dim = 1024
    cfg.settings.alias_union = True; cfg.settings.glossary_inject = True
    cfg.settings.glossary_lookup = True; cfg.settings.intent_gate = True
    cfg.settings.filtrar_fuera_dominio = True
    retr = SimpleRetriever(PostgresStore(), Qwen3Embedder(), get_reranker(),
                           top_bm25=cfg.settings.retrieval_pool_depth,
                           top_vector=cfg.settings.retrieval_pool_depth, llm=llm)

    tab = collections.defaultdict(lambda: collections.Counter())
    detalle = []
    for i, q in enumerate(rows, 1):
        gs = golds(q)
        docs = retr.retrieve(q["query"], top_k=TOPK)
        rk = rank_gold(docs, gs)
        ans = prev.get(q["query"]) or {}
        cito = bool(ans.get("cita_ok"))
        cat = q.get("category", "?")
        if cito:
            clase = "ACIERTA"
        elif rk is None:
            clase = "RETRIEVAL"        # el gold ni siquiera llego: generar mejor no lo salva
        else:
            clase = "GENERACION"       # el gold estaba ahi y no lo cito
        tab[cat][clase] += 1
        detalle.append({"query": q["query"], "category": cat, "rank_gold": rk,
                        "clase": clase, "n_cits": ans.get("n_cits")})
        if i % 20 == 0:
            print(f"  [{i}/{len(rows)}]", flush=True)

    # GUARDIA: si el gold no aparecio en el pool NI UNA VEZ en todo el set, lo mas probable
    # no es que el retrieval sea perfecto-malo: es que las claves del dict no matchean y la
    # comparacion nunca dio True. Un diagnostico que se equivoca en silencio es peor que no
    # tenerlo -- ya perdimos 6 h por un log que medía otra cosa.
    hallados = sum(1 for d in detalle if d["rank_gold"] is not None)
    if hallados == 0:
        raise SystemExit("ABORTA: el gold no aparecio en el pool en NINGUNA de las "
                         f"{len(detalle)} queries. Revisar las claves de rank_gold() contra "
                         "el dict que devuelve retrieve() antes de creerle a esta tabla.")
    print(f"\n[guardia] el gold aparecio en el pool en {hallados}/{len(detalle)} queries", flush=True)
    OUT.write_text(json.dumps(detalle, ensure_ascii=False, indent=1))
    tot = collections.Counter()
    print(f"\n{'categoria':16} {'ACIERTA':>8} {'RETRIEVAL':>10} {'GENERACION':>11}")
    for cat in sorted(tab):
        c = tab[cat]; tot.update(c)
        print(f"  {cat:16} {c['ACIERTA']:>6} {c['RETRIEVAL']:>10} {c['GENERACION']:>11}")
    n = sum(tot.values())
    print(f"  {'TOTAL':16} {tot['ACIERTA']:>6} {tot['RETRIEVAL']:>10} {tot['GENERACION']:>11}")
    fallos = tot['RETRIEVAL'] + tot['GENERACION']
    if fallos:
        print(f"\nDe los {fallos} fallos: {100*tot['RETRIEVAL']//fallos}% retrieval, "
              f"{100*tot['GENERACION']//fallos}% generacion")
    # Cuando el gold SI llego pero no se cito, importa DONDE llego: si viene en rank 8-9 el
    # problema puede ser de orden, no de que el modelo lo ignore.
    rks = [d["rank_gold"] for d in detalle if d["clase"] == "GENERACION" and d["rank_gold"] is not None]
    if rks:
        print(f"fallos de GENERACION con el gold en rank 0: {sum(1 for r in rks if r == 0)}/{len(rks)}"
              f"   mediana de rank {sorted(rks)[len(rks)//2]}")


if __name__ == "__main__":
    main()
