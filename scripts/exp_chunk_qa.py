"""QA / detector de anomalías de estructura para chunking.

Escanea TODOS los artículos y marca comportamientos raros que los chunkers regex
podrían estar perdiendo silenciosamente:
  - artículo grande (>UMBRAL) que quedaría en 1 solo chunk (estructura NO detectada)
  - parece glosario ("se entenderá por") pero no parsea defs
  - usa marcadores NO cubiertos por el regex actual (romanos I./II., ordinales
    "Primero.-", §, guiones) → estructura que se está perdiendo
  - fragmentos degenerados (tiny <20c o gigantes >3000c)

Sin GPU. Uso: ./venv-gpu/bin/python -m scripts.exp_chunk_qa [--show N]
"""
import re, sys
from collections import Counter
from src.storage.connection import with_connection
from psycopg.rows import dict_row
from scripts.exp_chunk_sweep import ck_inciso, ck_glossary, _MARK, _GLOS

BIG = 1500          # artículo "grande" que debería tener sub-estructura
TINY, HUGE = 20, 3000

# marcadores de estructura NO cubiertos por _MARK actual (a./1.)
ALT = {
    "romano":    re.compile(r"(?:^|\n)\s*[IVXLC]{1,4}[.)]\s+[A-ZÁÉÍÓÚÑ]"),
    "ordinal":   re.compile(r"(?:^|\n)\s*(?:Primero|Segundo|Tercero|Cuarto|Quinto|Sexto|Séptimo|Octavo|Noveno|Décimo)[°º]?\s*[.\-]"),
    "seccion§":  re.compile(r"§\s*\d"),
    "guion":     re.compile(r"(?:^|\n)\s*[-–—]\s+[A-ZÁÉÍÓÚÑ]"),
    "numeral°":  re.compile(r"(?:^|\n)\s*\d{1,2}[°º]\s+"),
}


def main():
    show = int(sys.argv[sys.argv.index("--show") + 1]) if "--show" in sys.argv else 0
    with with_connection() as c, c.cursor(row_factory=dict_row) as cur:
        cur.execute("SELECT id, id_norma, numero, texto FROM articulos WHERE texto IS NOT NULL AND texto<>''")
        arts = cur.fetchall()

    stats = Counter()
    anomalies = {"big_1chunk": [], "glos_noparse": [], "alt_markers": [], "degenerate": []}
    for a in arts:
        t = a["texto"]; L = len(t)
        stats["total"] += 1
        frags = ck_inciso(a)
        stats["inciso_1chunk"] += (len(frags) == 1)
        # 1) grande pero 1 solo chunk = estructura no detectada por _MARK
        if L > BIG and len(frags) == 1:
            # ¿tiene ALGÚN marcador alternativo?
            hits = [k for k, rx in ALT.items() if rx.search(t)]
            anomalies["big_1chunk"].append((a, L, hits))
            if hits:
                stats["big_1chunk_con_alt"] += 1
        # 2) glosario que no parsea
        if _GLOS.search(t):
            g = ck_glossary(a)
            if len(g) <= 1:
                anomalies["glos_noparse"].append((a, L))
        # 3) marcadores alternativos presentes (cobertura perdida)
        alts = [k for k, rx in ALT.items() if rx.search(t)]
        if alts and len(frags) == 1:
            anomalies["alt_markers"].append((a, alts))
            for k in alts:
                stats[f"alt_{k}"] += 1
        # 4) fragmentos degenerados
        for f in frags:
            if len(f) < TINY:
                stats["frag_tiny"] += 1
            elif len(f) > HUGE:
                stats["frag_huge"] += 1

    print("=== STATS ===")
    for k, v in sorted(stats.items()):
        print(f"  {k:22s} {v}")
    print("\n=== ANOMALÍAS (conteo) ===")
    for k, v in anomalies.items():
        print(f"  {k:16s} {len(v)}")
    print("\n=== marcadores alternativos NO cubiertos por _MARK (top) ===")
    alt_ct = Counter()
    for a, alts in anomalies["alt_markers"]:
        for k in alts:
            alt_ct[k] += 1
    for k, v in alt_ct.most_common():
        print(f"  {k:12s} {v} artículos")
    if show:
        print(f"\n=== ejemplos big_1chunk (primeros {show}) ===")
        for a, L, hits in anomalies["big_1chunk"][:show]:
            print(f"  [{a['id_norma']}/{a['numero']}] {L}c  alt={hits}  {a['texto'][:90]!r}")


if __name__ == "__main__":
    main()
