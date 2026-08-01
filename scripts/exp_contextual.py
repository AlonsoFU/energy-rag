"""EXP cheap-first: Contextual Retrieval (Anthropic) — contexto LLM por chunk.

Re-enriquece `contextual_text` de los chunks de NORMAS dadas con un resumen LLM
(ContextualEnricher) y re-embebe. A/B-safe: backup/revert. Mide retrievability
en las coloquiales de v3 cuyo gold cae en esas normas.

Uso:
  ./venv-gpu/bin/python -m scripts.exp_contextual backup 29819 1149788
  ./venv-gpu/bin/python -m scripts.exp_contextual apply  29819 1149788
  ./venv-gpu/bin/python -m scripts.exp_contextual revert
"""
import json, sys
from pathlib import Path
from psycopg.rows import dict_row
from src.storage.connection import with_connection

BACKUP = Path("data/eval/results/contextual_backup.json")


def chunks_of(normas):
    with with_connection() as c, c.cursor(row_factory=dict_row) as cur:
        cur.execute("""
            SELECT f.id, f.text, f.contextual_text, a.id_norma, a.numero, n.titulo AS norma_titulo
            FROM fragmentos f JOIN articulos a ON a.id=f.articulo_id
            JOIN normas n ON n.id_norma=a.id_norma
            WHERE a.id_norma = ANY(%s) ORDER BY f.id
        """, (list(normas),))
        return cur.fetchall()


def cmd_backup(normas):
    rows = chunks_of(normas)
    BACKUP.write_text(json.dumps([{"id": r["id"], "contextual_text": r["contextual_text"]} for r in rows], ensure_ascii=False))
    print(f"backup: {len(rows)} chunks (normas {normas}) -> {BACKUP}")


def cmd_apply(normas):
    from src.components.embedder import Qwen3Embedder
    from src.components.contextual import ContextualEnricher
    if not BACKUP.exists():
        print("ERROR: backup primero"); sys.exit(1)
    rows = chunks_of(normas)
    emb = Qwen3Embedder(); enr = ContextualEnricher()
    n = 0
    with with_connection() as c, c.cursor() as cur:
        for r in rows:
            ctx = enr.enrich(r["norma_titulo"], r["numero"], r["text"])  # resumen LLM + texto
            vec = emb.embed([ctx])[0]
            cur.execute("UPDATE fragmentos SET contextual_text=%s, embedding=%s WHERE id=%s", (ctx, vec, r["id"]))
            n += 1
            if n % 50 == 0:
                c.commit(); print(f"  ...{n}")
        c.commit()
    print(f"apply: {n} chunks re-enriquecidos (contextual LLM)")


def cmd_revert():
    from src.components.embedder import Qwen3Embedder
    if not BACKUP.exists():
        print("ERROR: no backup"); sys.exit(1)
    data = json.loads(BACKUP.read_text()); emb = Qwen3Embedder()
    with with_connection() as c, c.cursor() as cur:
        for d in data:
            vec = emb.embed([d["contextual_text"]])[0]
            cur.execute("UPDATE fragmentos SET contextual_text=%s, embedding=%s WHERE id=%s", (d["contextual_text"], vec, d["id"]))
        c.commit()
    print(f"revert: {len(data)} chunks restaurados")


if __name__ == "__main__":
    cmd = sys.argv[1]
    normas = sys.argv[2:]
    {"backup": lambda: cmd_backup(normas), "apply": lambda: cmd_apply(normas), "revert": cmd_revert}[cmd]()
