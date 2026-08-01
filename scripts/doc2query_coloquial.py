"""E6b — doc2query COLOQUIAL (Ollama): reemplaza el doc2query_text formal del mT5
por preguntas en lenguaje de la calle, que SÍ inyectan vocabulario coloquial
("me cortan la luz", "plata", "cuenta") al índice BM25 (tsv_aug). Solo fragmentos
in-domain (excluye normas off-domain). Sobrescribe doc2query_text → tsv_aug se
recomputa sola.

CAVEAT: las preguntas son sintéticas del mismo LLM; el número en coloquial_v2 puede
salir optimista (inyecta fraseo coloquial sobre los artículos gold). Medir y descontar.

Uso: HF_HUB_OFFLINE=1 ./venv-gpu/bin/python -m scripts.doc2query_coloquial
"""
from src.storage.connection import with_connection
from src.components.llm import get_llm_provider

OFF_DOMAIN = ("1007469", "1199483", "1207690", "1099982")
PROMPT = (
    "Eres un ciudadano chileno común (sin estudios legales). Lee este texto de una "
    "norma eléctrica y escribe 4 preguntas CORTAS en lenguaje COTIDIANO Y COLOQUIAL "
    "(como hablaría la gente en la calle: 'la luz', 'la cuenta', 'me cortan', 'plata', "
    "'los postes', 'los paneles') cuya respuesta esté en este texto. NO uses palabras "
    "técnicas ni legales. Una por línea, sin numerar.\n\nTEXTO:\n{t}\n\nPREGUNTAS:"
)


def main():
    llm = get_llm_provider()
    with with_connection() as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT f.id, f.text FROM fragmentos f JOIN articulos a ON a.id=f.articulo_id "
            "WHERE a.id_norma <> ALL(%s) AND length(f.text) > 80 ORDER BY f.id",
            (list(OFF_DOMAIN),),
        )
        rows = cur.fetchall()
    print(f"fragmentos in-domain a re-expandir: {len(rows)}", flush=True)
    done = 0
    for fid, text in rows:
        try:
            resp = llm.generate(PROMPT.format(t=text[:1400]), max_tokens=120)
            qs = [q.strip(" -•\t") for q in resp.text.splitlines() if len(q.strip()) > 10][:4]
            joined = " ".join(qs)
        except Exception:
            joined = ""
        if joined:
            with with_connection() as conn, conn.cursor() as cur:
                cur.execute("UPDATE fragmentos SET doc2query_text=%s WHERE id=%s", (joined, fid))
                conn.commit()
        done += 1
        if done % 100 == 0:
            print(f"  {done}/{len(rows)}  ej: {joined[:90]}", flush=True)
    print("LISTO doc2query coloquial", flush=True)


if __name__ == "__main__":
    main()
