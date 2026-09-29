"""Red golden de BUSQUEDA: los 10 articulos que devuelve retrieve.py para las 194 queries.

La BUSQUEDA si es bit-exacta (dos corridas dieron 194/194 el mismo orden), asi que un refactor
de `retrieve.py`/`vectorstore.py` se PRUEBA aca: si un solo puesto cambia, el refactor cambio el
comportamiento y se revierte. Tarda ~15 min contra las ~3 h de volver a redactar las 178
respuestas.

OJO, no vale lo mismo para `generate.py`: la REDACCION no es bit-exacta aunque la temperatura sea
0.0. Medido el 2026-09-28, mismo codigo y mismo corpus, la query "como se define Mora" dio 751,
419 y 419 caracteres en tres corridas (`qwen3:30b-a3b` es MoE). Para generate.py se usa
`scripts.exp_think_paired` + `scripts.comparar_corridas` y se mira el pareado, no la igualdad.

    PYTHONPATH=. venv/bin/python -m scripts.red_golden                          # graba la base
    PYTHONPATH=. venv/bin/python -m scripts.red_golden --salida /tmp/nueva.json
    PYTHONPATH=. venv/bin/python -m scripts.red_golden --comparar A.json B.json  # exit 1 si difiere
    PYTHONPATH=. venv/bin/python -m scripts.red_golden --autoprueba              # chequeo del comparador

La config es la de PRODUCCION: los defaults de `config.py`, sin ajustes a mano.
Reranker en GPU si hay VRAM libre; en fp32 da el mismo orden que en CPU (exp #88, 194/194).
Imprime recall@10 por set (el articulo gold entre los 10) — la metrica del buscador.
"""
import argparse
import json
import sys
import time
from pathlib import Path

SETS = {
    "dev": "data/eval/queries_operativas_v1.jsonl",
    "holdout": "data/eval/queries_fraseos_v1.jsonl",
    "reales": "data/eval/queries_publicas_gold_v1.jsonl",
}
BASE = Path("data/eval/redes/busqueda_base.json")


def _huella():
    """Igual que en exp_think_paired: dos corridas solo son comparables con el mismo corpus."""
    from src.storage.connection import with_connection
    with with_connection() as c:
        cur = c.cursor()
        cur.execute("SELECT (SELECT count(*) FROM articulos), (SELECT max(updated_at) FROM articulos), "
                    "(SELECT count(*) FROM fragmentos), (SELECT max(created_at) FROM fragmentos)")
        return [str(x) for x in cur.fetchone()]


def grabar(salida):
    from scripts.preguntar import _chequeos, _reranker_en_gpu_si_cabe
    from scripts.exp_think_paired import golds, _normalize_art
    _chequeos()
    _reranker_en_gpu_si_cabe()
    from src.components.embedder import Qwen3Embedder
    from src.components.llm import get_llm_provider
    from src.components.reranker import get_reranker
    from src.components.vectorstore import PostgresStore
    from src.core import config as cfg
    from src.pipelines.retrieve import SimpleRetriever

    retr = SimpleRetriever(PostgresStore(), Qwen3Embedder(), get_reranker(),
                           top_bm25=cfg.settings.retrieval_pool_depth,
                           top_vector=cfg.settings.retrieval_pool_depth, llm=get_llm_provider())

    red, t0 = {}, time.time()
    for nombre, ruta in SETS.items():
        rows = [json.loads(l) for l in Path(ruta).read_text().splitlines() if l.strip()]
        red[nombre] = []
        for i, q in enumerate(rows):
            docs = retr.retrieve(q["query"], top_k=10)
            top = [[str(d.get("id_norma")), _normalize_art(str(d.get("articulo_numero")))] for d in docs]
            red[nombre].append({"query": q["query"], "top10": top,
                                "gold_en_top10": bool(golds(q) & {tuple(x) for x in top})})
            if (i + 1) % 10 == 0:
                print(f"  {nombre} {i+1}/{len(rows)}  [{time.time()-t0:.0f} s]", flush=True)
    salida.parent.mkdir(parents=True, exist_ok=True)
    salida.write_text(json.dumps({"db_huella": _huella(), "red": red}, ensure_ascii=False, indent=1))
    print(f"\n  grabada en {salida}  [{time.time()-t0:.0f} s]")
    recall(red)


def recall(red):
    print("\n  recall@10 (el articulo gold entre los 10 que muestra el buscador):")
    for nombre, filas in red.items():
        ok = sum(f["gold_en_top10"] for f in filas)
        print(f"    {nombre:8} {ok}/{len(filas)} = {100*ok/len(filas):.0f} %")


def comparar(a, b):
    """0 si el orden es identico en todas las queries; 1 si algo cambio."""
    A, B = json.loads(Path(a).read_text()), json.loads(Path(b).read_text())
    if A["db_huella"] != B["db_huella"]:
        print(f"  ⚠️  CORPUS DISTINTO, la comparacion no vale:\n      {A['db_huella']}\n      {B['db_huella']}")
        return 1
    difs = [(n, f["query"]) for n in A["red"]
            for f, g in zip(A["red"][n], B["red"][n]) if f["top10"] != g["top10"]]
    faltan = [n for n in A["red"] if len(A["red"][n]) != len(B["red"].get(n, []))]
    if faltan:
        print(f"  ⚠️  sets con distinta cantidad de queries: {faltan}")
        return 1
    total = sum(len(v) for v in A["red"].values())
    if not difs:
        print(f"  ✓ orden identico en {total}/{total} queries")
        return 0
    print(f"  ✗ el orden cambio en {len(difs)} de {total} queries:")
    for n, q in difs[:10]:
        print(f"    [{n}] {q[:100]}")
    if len(difs) > 10:
        print(f"    … y {len(difs)-10} mas")
    recall(B["red"])
    return 1


def autoprueba():
    """El comparador tiene que ver una diferencia de un solo puesto, y el corpus distinto."""
    import tempfile
    d = Path(tempfile.mkdtemp())
    red = {"dev": [{"query": "q1", "top10": [["1", "5"], ["2", "7"]], "gold_en_top10": True}]}
    (d / "a.json").write_text(json.dumps({"db_huella": ["h"], "red": red}))
    (d / "b.json").write_text(json.dumps({"db_huella": ["h"], "red": red}))
    assert comparar(d / "a.json", d / "b.json") == 0
    red2 = {"dev": [{"query": "q1", "top10": [["2", "7"], ["1", "5"]], "gold_en_top10": True}]}
    (d / "c.json").write_text(json.dumps({"db_huella": ["h"], "red": red2}))
    assert comparar(d / "a.json", d / "c.json") == 1, "no vio el cambio de orden"
    (d / "e.json").write_text(json.dumps({"db_huella": ["otra"], "red": red}))
    assert comparar(d / "a.json", d / "e.json") == 1, "no vio el corpus distinto"
    print("  ✓ autoprueba ok")
    return 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--salida", type=Path, default=BASE)
    ap.add_argument("--comparar", nargs=2, metavar=("A", "B"))
    ap.add_argument("--autoprueba", action="store_true")
    a = ap.parse_args()
    if a.autoprueba:
        sys.exit(autoprueba())
    elif a.comparar:
        sys.exit(comparar(*a.comparar))
    else:
        grabar(a.salida)
