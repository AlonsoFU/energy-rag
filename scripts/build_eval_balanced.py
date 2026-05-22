"""Build a 3-category balanced eval set.

Categories:
  - in_domain         : energy-domain queries (auto from glossaries, filtered)
  - off_domain_corpus : queries about docs that ARE in the corpus but not energy
                        (telepeaje, tránsito, sueldos públicos)
  - off_corpus        : queries about topics NOT in the corpus at all (cooking,
                        medicine, invented words, ...)

Each category measures a distinct behavior — do NOT aggregate.
"""
import argparse
import json
from pathlib import Path
from psycopg.rows import dict_row
from src.storage.connection import with_connection

# Domain-energy normas (verified via DB titulo in earlier session).
ENERGY_NORMAS = (
    "1146553",  # DECRETO 10 tarificación
    "1112591",  # RESOLUCIÓN 711 planificación transmisión
    "250604",   # DECRETO 62 transferencias de potencia
    "1160108",  # DECRETO 37 sistemas de transmisión
    "1005169",  # LEY 20365 sistemas solares térmicos
    "1183783",  # LEY 21499 biocombustibles sólidos
    "1155887",  # LEY 21305 eficiencia energética
    "29819",    # LEY 18410 SEC
)

# Off-domain-but-in-corpus normas (we keep them: the system CAN answer them
# because the docs are loaded — this measures behavior on out-of-product
# in-corpus questions, NOT a defect).
OFF_DOMAIN_NORMAS = (
    "1207690",  # DECRETO 262 telepeaje vial
    "1007469",  # DFL 1 Ley de Tránsito
    "1199483",  # LEY 21647 reajuste sector público
)

SQL_AUTO = """
WITH ranked AS (
  SELECT c.id AS concepto_id, c.nombre, a.numero AS articulo_numero, a.id_norma,
         length(c.definicion) AS def_len,
         ROW_NUMBER() OVER (
           PARTITION BY c.id
           -- Most-recent (vigente) defining norma wins, same rule as inject.
           ORDER BY n.fecha_publicacion DESC NULLS LAST, a.id_norma, a.orden
         ) AS rn
    FROM conceptos c
    -- ONLY define_termino edges: the expected article must be where the term
    -- is DEFINED, not merely mentioned. This makes expected_norma well-defined
    -- instead of an arbitrary mention.
    JOIN referencias r ON r.destino_concepto_id = c.id
                      AND r.tipo_relacion = 'define_termino'
    JOIN articulos   a ON a.id = r.origen_articulo_id
    JOIN normas      n ON n.id_norma = a.id_norma
   WHERE length(c.nombre) BETWEEN 3 AND 60
     AND c.nombre NOT LIKE '%%clasificados%%'
     AND a.id_norma = ANY(%s::text[])
)
SELECT nombre, articulo_numero, id_norma, def_len
  FROM ranked
 WHERE rn = 1
 ORDER BY def_len DESC
 LIMIT %s;
"""

# Hand-curated off-corpus queries. None of these terms should appear in the
# corpus; the system MUST refuse (negative_correct).
OFF_CORPUS = [
    # Originales (15)
    {"query": "qué es xenobalbúrgico"},
    {"query": "cuál es la receta del pisco sour"},
    {"query": "cómo se cura la diabetes tipo 1"},
    {"query": "quién ganó el mundial de fútbol 1962"},
    {"query": "qué es la teoría de la relatividad"},
    {"query": "fórmula química del ácido sulfúrico"},
    {"query": "cuántos kilómetros mide la Gran Muralla China"},
    {"query": "cómo se prepara una paella valenciana"},
    {"query": "qué es el síndrome de Asperger"},
    {"query": "biografía de Pablo Neruda"},
    {"query": "cómo funciona un motor de combustión interna"},
    {"query": "qué es la fotosíntesis"},
    {"query": "horario del metro de Santiago"},
    {"query": "precio del dólar hoy"},
    {"query": "qué es Bitcoin"},
    # Expansión (15 más)
    {"query": "cómo se hace una empanada chilena"},                # cocina
    {"query": "qué es el ADN"},                                     # biología
    {"query": "cuándo nació Einstein"},                             # historia
    {"query": "qué es la inteligencia artificial"},                 # tech (no en corpus)
    {"query": "cuál es la capital de Australia"},                   # geografía
    {"query": "cómo se calcula el área de un triángulo"},          # matemática
    {"query": "qué es el cambio climático"},                       # ambiental gen
    {"query": "qué hace un cardiólogo"},                            # medicina
    {"query": "cómo se conjuga el verbo haber"},                   # lingüística
    {"query": "qué es el ratimagusto"},                             # palabra inventada
    {"query": "cuál es la mejor pizza de Chile"},                   # opinión/gastronomía
    {"query": "qué es el yoga"},                                    # bienestar
    {"query": "cómo se hace pan amasado"},                          # cocina
    {"query": "qué es la mecánica cuántica"},                       # física
    {"query": "cuáles son las películas de Almodóvar"},             # cine
]

# Multi-phrasing for in-domain to expand the set without inventing concepts.
# Each concept generates N variants — same expected_norma+articulo.
IN_DOMAIN_PHRASINGS = (
    "qué es {x}",
    "definición de {x}",
    "qué significa {x}",
)


def fetch_by_normas(normas: tuple[str, ...], limit: int,
                    phrasings: tuple[str, ...] = ("qué es {x}",)) -> list[dict]:
    """Fetch concepts and emit one row per (concept, phrasing) variant.

    `limit` caps the number of DISTINCT concepts (not rows). Phrasings let us
    expand the eval set without inventing terms — same concept asked 2-3 ways
    produces N rows pointing to the same expected_norma+articulo.
    """
    out = []
    with with_connection() as conn, conn.cursor(row_factory=dict_row) as cur:
        cur.execute(SQL_AUTO, (list(normas), limit))
        for rec in cur.fetchall():
            for tpl in phrasings:
                out.append({
                    "query": tpl.format(x=rec["nombre"].strip()),
                    "expected_norma": rec["id_norma"],
                    "expected_articulo": str(rec["articulo_numero"]).strip(),
                    "category": None,
                })
    return out


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--n-in", type=int, default=50)
    p.add_argument("--n-off-corpus-in-domain", type=int, default=15)
    p.add_argument("--output", type=Path,
                   default=Path("data/eval/queries_balanced.jsonl"))
    a = p.parse_args()

    # in_domain: cap CONCEPTS (not rows), then expand with phrasings.
    in_dom = fetch_by_normas(ENERGY_NORMAS, a.n_in,
                              phrasings=IN_DOMAIN_PHRASINGS)
    for r in in_dom: r["category"] = "in_domain"

    off_in = fetch_by_normas(OFF_DOMAIN_NORMAS, a.n_off_corpus_in_domain)
    for r in off_in: r["category"] = "off_domain_corpus"

    off = [{**q, "expected_norma": None, "expected_articulo": None,
            "category": "off_corpus"} for q in OFF_CORPUS]

    rows = in_dom + off_in + off
    a.output.parent.mkdir(parents=True, exist_ok=True)
    with a.output.open("w", encoding="utf-8") as fh:
        for r in rows:
            fh.write(json.dumps(r, ensure_ascii=False) + "\n")
    by_cat = {}
    for r in rows: by_cat[r["category"]] = by_cat.get(r["category"], 0) + 1
    print(f"escrito: {a.output} con {len(rows)} queries")
    for k, v in by_cat.items(): print(f"  {k}: {v}")


if __name__ == "__main__":
    main()
