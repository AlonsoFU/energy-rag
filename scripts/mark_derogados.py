"""D1 (mitad OFFLINE): marca artículos DEROGADOS detectables en el propio corpus.

Contexto: D1 completo (vigencia/derogación a nivel de NORMA) necesita BCN, que hoy responde
**429 "Service limit has been reached"** en `obtxml` — ver handoff. Esta es la parte que SÍ se
puede hacer sin red: artículos cuyo texto se auto-declara derogado.

    258171/23   "Artículo 23°.- Derogado."
    16121/5°    "Artículo 5°.- Derogado"
    150669/23   "Artículo 23.- ... Derogado."   (con líneas de enmienda intercaladas)

Detección conservadora: artículo CORTO (<260 chars) cuyo cuerpo es esencialmente "Derogado".
No usa heurísticas laxas: un artículo largo que MENCIONA "derógase" está derogando a OTRA norma,
no a sí mismo (ej 1149788/segundo "Derógase el decreto supremo Nº 71...").

⚠️ ALCANCE REAL MEDIDO: solo 3 artículos, y 0 citas a ellos en los evals actuales (son stubs
de 22-66 chars, el retrieval no los sube). El riesgo legal de verdad es la derogación a nivel
de NORMA COMPLETA, que sigue BLOQUEADA por BCN.

Uso:  PYTHONPATH=. venv/bin/python -m scripts.mark_derogados          (dry)
      WRITE=1 PYTHONPATH=. venv/bin/python -m scripts.mark_derogados  (persiste)
"""
import os, re
from src.storage.connection import with_connection

WRITE = os.environ.get("WRITE") == "1"
MAX_LEN = 260


def detectar():
    with with_connection() as conn, conn.cursor() as cur:
        cur.execute("SELECT id, id_norma, numero, texto FROM articulos WHERE texto IS NOT NULL")
        arts = cur.fetchall()
    out = []
    for aid, n, a, t in arts:
        if len(t) >= MAX_LEN or not re.search(r"[Dd]erogad[oa]", t):
            continue
        # el cuerpo, sin encabezado ni lineas de enmienda, debe ser ~"Derogado"
        cuerpo = re.sub(r"(?m)^\s*(?:Ley|Decreto|DFL|Art\.|D\.O\.)\b.*$", "", t)
        # OJO: el cuantificador PEREZOSO ([^\n]{0,20}?) dejaba el numero sin comer
        # ("Artículo 23°.- Derogado." -> "23°.- Derogado.") y nada matcheaba. Explicito.
        cuerpo = re.sub(r"(?i)^\s*art[íi]culo\s*[\w°º]+\s*[.:\-]*\s*", "", cuerpo.strip())
        if re.fullmatch(r"(?is)\s*derogad[oa]s?\s*\.?\s*", cuerpo):
            out.append((aid, n, a, t.strip()[:60]))
    return out


def main():
    d = detectar()
    print(f"articulos DEROGADOS (auto-declarados): {len(d)}")
    for _, n, a, s in d:
        print(f"   {n}/{a:12} | {s}")
    if not WRITE:
        print("\n(dry-run; WRITE=1 para persistir la marca)")
        return
    with with_connection() as conn, conn.cursor() as cur:
        cur.execute("ALTER TABLE articulos ADD COLUMN IF NOT EXISTS derogado boolean DEFAULT false")
        for aid, *_ in d:
            cur.execute("UPDATE articulos SET derogado = true WHERE id = %s", (aid,))
        conn.commit()
        cur.execute("SELECT count(*) FROM articulos WHERE derogado")
        print(f"\n[WRITE] marcados: {cur.fetchone()[0]}")


if __name__ == "__main__":
    main()
