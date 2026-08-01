"""Exp #2-AUTO: derivar el vocabulario controlado del CORPUS (sin curación a mano).

Escanea fragmentos por patrones definitorios chilenos y extrae pares
(término_legal ↔ alias/acrónimo):
  - "<Término>, en adelante 'X'"      → acrónimo/nombre corto legal
  - "se entiende por <X> ..."          → término definido
  - "para los efectos ... <X> es ..."  → término definido

OBJETIVO: medir si la extracción AUTOMÁTICA generaliza — ¿cuántos pares saca?, y
¿cubre los 4 casos coloquiales que la curación a mano rescata (87/118/2/212)?

Hipótesis a verificar: el corpus da sinónimos/acrónimos LEGALES (SEC, VNR, Panel),
NO paráfrasis COLOQUIALES ("tope de ganancia"→"tasa de descuento"). Si es así, auto
escala para acrónimos pero NO resuelve el muro coloquial → son mecanismos distintos.

Uso: PYTHONPATH=. venv/bin/python -m scripts.exp_alias_auto
"""
import re
from src.storage.connection import with_connection
from psycopg.rows import dict_row

# alias legal a apender que rescata cada caso (lo que el mapa CURADO usa)
CURATED_TARGET = {
    "87":  "planificación de la transmisión",
    "118": "tasa de descuento anualidad valor de inversión",
    "2":   "capacidad instalada equipamiento de generación",
    "212": "Panel de Expertos financiamiento",
}

# "<Término(8-70)>, en adelante 'alias(2-45)'"  (acrónimo o nombre corto)
RE_ADELANTE = re.compile(
    r'([A-ZÁÉÍÓÚÑ][\wáéíóúñ ]{7,69}?),?\s+en adelante,?\s*["“]?([^"”.;]{2,45}?)["”]', re.I)
# "se entiende por <X(2-60)>"
RE_ENTIENDE = re.compile(r'se entiende por\s+["“]?([^"”.;:,]{2,60})', re.I)


def main():
    with with_connection() as c, c.cursor(row_factory=dict_row) as cur:
        cur.execute("SELECT text FROM fragmentos WHERE text ~* 'en adelante|se entiende por|para los efectos'")
        texts = [r["text"] for r in cur.fetchall()]
    pairs, terms = set(), set()
    for t in texts:
        for full, alias in RE_ADELANTE.findall(t):
            full, alias = full.strip(), alias.strip()
            if 8 <= len(full) and 2 <= len(alias) <= 45 and alias.lower() != full.lower():
                pairs.add((full, alias))
        for term in RE_ENTIENDE.findall(t):
            terms.add(term.strip())
    print(f"=== Exp #2-AUTO: extracción del corpus ===", flush=True)
    print(f"pares (término ↔ en-adelante/acrónimo): {len(pairs)}", flush=True)
    print(f"términos 'se entiende por': {len(terms)}", flush=True)
    print("\n--- muestra pares legal↔alias ---", flush=True)
    for full, alias in sorted(pairs)[:20]:
        print(f"  «{alias}»  ←  {full[:60]}", flush=True)
    # ¿La extracción auto cubre los 4 casos coloquiales?
    blob = " || ".join(f"{f} :: {a}" for f, a in pairs) + " || " + " || ".join(terms)
    blob_l = blob.lower()
    print("\n--- cobertura de los 4 casos coloquiales (lo que rescata la curación) ---", flush=True)
    for caso, target in CURATED_TARGET.items():
        head = target.split()[0].lower()  # palabra clave del término
        hit = head in blob_l
        print(f"  caso {caso:4s} target='{target[:45]}'  auto_cubre={'sí' if hit else 'NO'}", flush=True)


if __name__ == "__main__":
    main()
