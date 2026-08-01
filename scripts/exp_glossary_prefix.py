"""EXP glosario term-prefix (determinista) — ataca 'definición hundida'.

Para chunks de artículos-glosario ('se entiende/entenderá por' + defs 'x) Término:'),
antepone a contextual_text la LISTA de términos definidos EN ESE chunk, extraídos
deterministamente. Así una query 'tasa de actualización' matchea fuerte el chunk que
la define (hoy pierde contra el artículo monotemático). Re-embebe SOLO esos chunks.

A/B-safe: 'backup' guarda (id, contextual_text, embedding) antes; 'revert' restaura.
Uso:
  ./venv-gpu/bin/python -m scripts.exp_glossary_prefix backup
  ./venv-gpu/bin/python -m scripts.exp_glossary_prefix apply
  ./venv-gpu/bin/python -m scripts.exp_glossary_prefix revert
  ./venv-gpu/bin/python -m scripts.exp_glossary_prefix show     # solo imprime prefijos, no toca DB
"""
import json
import re
import sys
from pathlib import Path

from psycopg.rows import dict_row
from src.storage.connection import with_connection

BACKUP = Path("data/eval/results/glossary_prefix_backup.json")

GLOSS_SQL = """
SELECT f.id, f.articulo_id, f.chunk_index, f.text, f.contextual_text,
       a.id_norma, a.numero
FROM articulos a JOIN fragmentos f ON f.articulo_id = a.id
WHERE a.texto ~ 'se entender[áa] por|se entiende por'
  AND a.texto ~ '[a-z]\\) [A-ZÁÉÍÓÚÑ]'
ORDER BY a.id_norma, a.numero, f.chunk_index
"""

# formato-1: 'letra) Término:'  (glosario apretado, ej. LGSE 225)
TERM_RE = re.compile(r"(?:^|[\s.;])([a-zñA-ZÑ]{1,3})\)\s+([A-ZÁÉÍÓÚÑ][^:\n]{2,70}?):")
# formato-2: 'Término:' al inicio del chunk (1-def-por-chunk, ej. 250604/13)
LEAD_RE = re.compile(r"^([A-ZÁÉÍÓÚÑ][^:\n]{2,70}?):")
# verbos de modificación legal → NO es definición (falsos positivos)
AMEND = ("sustitúyese", "incorpórase", "agrégase", "reemplázase", "modifícase",
         "intercálase", "elimínase", "derógase", "suprímese", "reemplázase")


def _ok_term(t: str) -> bool:
    tl = t.lower()
    return (2 < len(t) <= 70 and "artículo" not in tl
            and not any(tl.startswith(v) for v in AMEND))


def extract_terms(text: str) -> list[str]:
    seen, out = set(), []
    cands = [m[1] for m in TERM_RE.findall(text)]
    lead = LEAD_RE.match(text.strip())
    if lead:
        cands.insert(0, lead.group(1))
    for term in cands:
        t = re.sub(r"\s+", " ", term).strip()
        if _ok_term(t) and t.lower() not in seen:
            seen.add(t.lower()); out.append(t)
    return out


def build_prefix(terms: list[str]) -> str:
    return f"Definiciones de: {'; '.join(terms)}." if terms else ""


def _rows():
    with with_connection() as conn, conn.cursor(row_factory=dict_row) as cur:
        cur.execute(GLOSS_SQL)
        return cur.fetchall()


def cmd_show():
    rows = _rows()
    n_terms = 0
    for r in rows:
        terms = extract_terms(r["text"])
        n_terms += len(terms)
        if terms:
            print(f"{r['id_norma']}/{r['numero']} ck{r['chunk_index']}: {build_prefix(terms)[:160]}")
    print(f"\n{len(rows)} chunks, {n_terms} términos extraídos, "
          f"{sum(1 for r in rows if extract_terms(r['text']))} chunks con prefijo")


def cmd_backup():
    rows = _rows()
    data = [{"id": r["id"], "contextual_text": r["contextual_text"]} for r in rows]
    BACKUP.parent.mkdir(parents=True, exist_ok=True)
    BACKUP.write_text(json.dumps(data, ensure_ascii=False))
    print(f"backup: {len(data)} chunks -> {BACKUP}")


def cmd_apply():
    from src.components.embedder import Qwen3Embedder
    if not BACKUP.exists():
        print("ERROR: corré 'backup' primero."); sys.exit(1)
    rows = _rows()
    emb = Qwen3Embedder()
    n = 0
    with with_connection() as conn, conn.cursor() as cur:
        for r in rows:
            terms = extract_terms(r["text"])
            if not terms:
                continue
            prefix = build_prefix(terms)
            # idempotente: no re-prependear si ya lo tiene
            base = r["contextual_text"]
            if base.startswith("Definiciones de:"):
                continue
            new_ctx = f"{prefix}\n\n{base}"
            vec = emb.embed([new_ctx])[0]
            cur.execute(
                "UPDATE fragmentos SET contextual_text=%s, embedding=%s WHERE id=%s",
                (new_ctx, vec, r["id"]),
            )
            n += 1
        conn.commit()
    print(f"apply: {n} chunks re-embebidos con term-prefix")


def cmd_revert():
    if not BACKUP.exists():
        print("ERROR: no hay backup."); sys.exit(1)
    from src.components.embedder import Qwen3Embedder
    data = json.loads(BACKUP.read_text())
    emb = Qwen3Embedder()
    with with_connection() as conn, conn.cursor() as cur:
        for d in data:
            vec = emb.embed([d["contextual_text"]])[0]
            cur.execute(
                "UPDATE fragmentos SET contextual_text=%s, embedding=%s WHERE id=%s",
                (d["contextual_text"], vec, d["id"]),
            )
        conn.commit()
    print(f"revert: {len(data)} chunks restaurados")


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "show"
    {"show": cmd_show, "backup": cmd_backup, "apply": cmd_apply, "revert": cmd_revert}[cmd]()
