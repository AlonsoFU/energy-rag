"""FASE C paso 1 — generar dataset contrastivo coloquial→artículo (Ollama, offline).

Para cada artículo de las 5 normas eléctricas (MENOS los 39 golds de coloquial_v2,
que se reservan como held-out limpio), genera 2 preguntas en lenguaje COTIDIANO cuya
respuesta es ese artículo. Salida JSONL: {"q": coloquial, "norma":, "art":, "texto":}.

El held-out real = queries_coloquial_v2 (esas 39 preguntas NUNCA se generan aquí, y
sus artículos gold se EXCLUYEN del entrenamiento → la mejora, si la hay, es
generalización de registro, no memorización del artículo).

Uso: HF_HUB_OFFLINE=1 ./venv-gpu/bin/python -m scripts.ft_gen_dataset
"""
import json
from src.storage.connection import with_connection
from src.components.llm import get_llm_provider

NORMS = ("258171", "250604", "1149788", "202975", "29819")
OUT = "data/eval/ft_pairs.jsonl"

PROMPT = (
    "Eres un ciudadano chileno común (sin formación legal) preguntando por la luz, "
    "las cuentas, los cortes, los postes, los paneles, las tarifas, etc.\n"
    "Lee este artículo de la normativa eléctrica y escribe 2 preguntas en lenguaje "
    "COTIDIANO Y COLOQUIAL (como hablaría la gente, sin términos técnicos ni legales) "
    "cuya respuesta esté en este artículo. Una pregunta por línea, sin numeración.\n"
    "NO uses palabras del artículo como 'remuneración', 'concesión', 'coordinador', "
    "'discrepancia'; traduce a lenguaje de la calle.\n\n"
    "ARTÍCULO:\n{texto}\n\nDOS PREGUNTAS COTIDIANAS:"
)


def held_out_gold_arts():
    arts = set()
    for l in open("data/eval/queries_coloquial_v2.jsonl"):
        d = json.loads(l)
        if d.get("category") == "cx_coloquial" and d.get("expected_norma"):
            arts.add((str(d["expected_norma"]), str(d["expected_articulo"])))
    return arts


def main():
    held = held_out_gold_arts()
    llm = get_llm_provider()
    with with_connection() as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT id_norma, numero, texto FROM articulos "
            "WHERE id_norma = ANY(%s) AND length(texto) > 120 ORDER BY id_norma, numero",
            (list(NORMS),),
        )
        rows = cur.fetchall()
    n_written = 0
    with open(OUT, "w") as f:
        for i, (norma, art, texto) in enumerate(rows):
            if (str(norma), str(art)) in held:
                continue  # held-out: nunca entrenar sobre el artículo gold real
            try:
                resp = llm.generate(PROMPT.format(texto=texto[:1800]), max_tokens=120)
                qs = [q.strip(" -•\t") for q in resp.text.splitlines() if len(q.strip()) > 12][:2]
            except Exception:
                qs = []
            for q in qs:
                f.write(json.dumps({"q": q, "norma": str(norma), "art": str(art),
                                    "texto": texto}, ensure_ascii=False) + "\n")
                n_written += 1
            if (i + 1) % 50 == 0:
                f.flush()
                print(f"  {i+1}/{len(rows)} arts, {n_written} pares", flush=True)
    print(f"LISTO: {n_written} pares -> {OUT}")


if __name__ == "__main__":
    main()
