"""Los numeros del sistema, GENERADOS. Para que los docs no se podrezcan.

    PYTHONPATH=. venv/bin/python -m scripts.estado            # legible
    PYTHONPATH=. venv/bin/python -m scripts.estado --markdown  # tablas para pegar en docs/sistema/

Regla del proyecto: ningun numero de `docs/sistema/` se escribe a mano. Si un numero de aca
no coincide con el doc, el doc esta viejo.
"""
import argparse
import json
from pathlib import Path

RED = Path("data/eval/redes/busqueda_base.json")
ADOPTADOS = ["selfcons_temperature", "self_consistency_n", "answer_quote_only", "answer_quote_max",
             "answer_quote_reatribuir", "answer_prosa_marcar", "answer_think", "embed_4b_dense",
             "embed_4b_dim", "alias_union", "glossary_inject", "glossary_lookup", "intent_gate",
             "ambiguity_disclose", "filtrar_fuera_dominio", "retrieval_pool_depth",
             "ollama_num_ctx", "llm_default"]


def corpus():
    from src.storage.connection import with_connection
    with with_connection() as c:
        cur = c.cursor()
        cur.execute("""SELECT (SELECT count(*) FROM normas),
                              (SELECT count(*) FROM articulos),
                              (SELECT count(*) FROM articulos WHERE coalesce(derogado,false)),
                              (SELECT count(*) FROM fragmentos),
                              (SELECT count(*) FROM conceptos),
                              (SELECT count(*) FROM norma_evento),
                              (SELECT max(updated_at) FROM articulos),
                              (SELECT max(created_at) FROM fragmentos)""")
        n, a, ader, f, co, ev, ua, cf = cur.fetchone()
    return {"normas": n, "articulos": a, "articulos derogados": ader, "fragmentos": f,
            "conceptos": co, "eventos del monitor": ev,
            "db_huella": [str(a), str(ua), str(f), str(cf)]}


def config_adoptada():
    from src.core import config as cfg
    return {k: getattr(cfg.settings, k, "—") for k in ADOPTADOS}


def buscador():
    """recall@10 por set, de la red golden. None si no esta grabada."""
    if not RED.exists():
        return None
    red = json.loads(RED.read_text())["red"]
    return {k: (sum(f["gold_en_top10"] for f in v), len(v)) for k, v in red.items()}


def citas():
    """cita_ok / cita_limpia de las corridas vigentes, si estan en disco."""
    out = {}
    for nombre in ("l69_dev", "l69_holdout", "pub_final"):
        p = Path(f"data/eval/results/{nombre}/result.json")
        if not p.exists():
            continue
        det = json.loads(p.read_text())["detail"]
        hechas = [r for r in det if isinstance(r.get("on"), dict)]
        out[nombre] = (sum(r["on"]["cita_ok"] for r in hechas),
                       sum(r["on"]["cita_limpia"] for r in hechas), len(det))
    return out


def main(markdown=False):
    c, cf, b, ci = corpus(), config_adoptada(), buscador(), citas()
    if markdown:
        print("| corpus | |\n|---|---|")
        for k, v in c.items():
            print(f"| {k} | {v if not isinstance(v, list) else '`' + ' · '.join(v) + '`'} |")
        print("\n| config adoptada | |\n|---|---|")
        for k, v in cf.items():
            print(f"| `{k}` | {v} |")
        if b:
            print("\n| set | recall@10 |\n|---|---|")
            for k, (ok, n) in b.items():
                print(f"| {k} | {ok}/{n} = {100*ok/n:.0f} % |")
        if ci:
            print("\n| corrida | cita_ok | cita_limpia | n |\n|---|---|---|---|")
            for k, (ok, li, n) in ci.items():
                print(f"| {k} | {ok} | {li} | {n} |")
        return
    print("CORPUS")
    for k, v in c.items():
        print(f"  {k:22} {v}")
    print("\nCONFIG ADOPTADA")
    for k, v in cf.items():
        print(f"  {k:26} {v}")
    print("\nBUSCADOR (recall@10, red golden)" if b else "\nBUSCADOR: falta la red golden "
          "(PYTHONPATH=. venv/bin/python -m scripts.red_golden)")
    for k, (ok, n) in (b or {}).items():
        print(f"  {k:10} {ok}/{n} = {100*ok/n:.0f} %")
    print("\nCITAS (corridas en disco)")
    for k, (ok, li, n) in ci.items():
        print(f"  {k:14} cita_ok {ok}  cita_limpia {li}  de {n}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--markdown", action="store_true")
    main(**vars(ap.parse_args()))
