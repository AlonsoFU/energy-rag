"""exp: contexto chico para el embedder 4B en CPU (causa de los cortes por falta de RAM).

Hallazgo (2026-09-14): `ollama ps` mostro `qwen3-embedding:4b  9.8 GB  100% CPU  ctx 32768`.
`_embed_4b_query` manda solo `num_gpu: 0`, sin `num_ctx`, y Ollama 0.22.1 aplica su contexto por
defecto (32768) aunque el modelo corra en CPU. Esa reserva llena la RAM de 14 GB y el sistema
mato dos corridas de diagnostico. Lo mas largo que se embebe mide ~1471 tokens (contextual_text)
y ~3081 (fragmentos_definicion), asi que 32768 no hace falta.

Compara, para cada num_ctx candidato, los vectores nuevos contra los GUARDADOS en la DB
(`embedding_4b_1024`, primeras 1024 dims normalizadas). No recarga el modelo con 32768: eso es
justo lo que provoca el corte. `truncate: false` hace que Ollama FALLE si un texto no cabe, en vez
de truncarlo en silencio.

Criterio FIJADO ANTES:
  adoptar num_ctx=N si  coseno minimo >= 0.9999 contra lo guardado en TODOS los textos
                    Y   ningun error de "no cabe"
                    Y   la RAM del embedder baja
  si no se cumple con 4096 -> no se toca el codigo.
Caveat: lo guardado pudo calcularse en GPU y esto corre en CPU; diferencias numericas de ese tipo
dan coseno > 0.9999. Si el minimo cae por debajo, se revisa antes de concluir.

  env PYTHONPATH=. CTX=4096,2048 venv/bin/python -m scripts.exp_embed_ctx
"""
import json, math, os, urllib.request
from src.storage.connection import with_connection

M = "qwen3-embedding:4b"
URL = "http://localhost:11434"


def post(path, payload, timeout=600):
    req = urllib.request.Request(URL + path, data=json.dumps(payload).encode(),
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read())


def ram_embedder():
    with urllib.request.urlopen(URL + "/api/ps", timeout=10) as r:
        for m in json.loads(r.read()).get("models", []):
            if m["name"].startswith(M):
                return (m.get("size", 0) - m.get("size_vram", 0)) / 1e9, m.get("context_length")
    return None, None


def mrl(v):
    s = v[:1024]
    n = math.sqrt(sum(x * x for x in s)) or 1.0
    return [x / n for x in s]


def coseno(a, b):
    return sum(x * y for x, y in zip(a, b))


def muestra():
    with with_connection() as c, c.cursor() as cur:
        out = []
        cur.execute("""SELECT 'frag-largo', contextual_text, embedding_4b_1024::text FROM fragmentos
                       WHERE embedding_4b_1024 IS NOT NULL ORDER BY length(contextual_text) DESC LIMIT 3""")
        out += cur.fetchall()
        cur.execute("""SELECT 'frag-azar', contextual_text, embedding_4b_1024::text FROM fragmentos
                       WHERE embedding_4b_1024 IS NOT NULL ORDER BY md5(id::text) LIMIT 4""")
        out += cur.fetchall()
        cur.execute("""SELECT 'def-largo', texto, embedding_4b_1024::text FROM fragmentos_definicion
                       WHERE embedding_4b_1024 IS NOT NULL ORDER BY length(texto) DESC LIMIT 2""")
        out += cur.fetchall()
    return [(k, t, [float(x) for x in e.strip("[]").split(",")]) for k, t, e in out]


def main():
    textos = muestra()
    print(f"textos de muestra: {len(textos)} | largos max: {max(len(t) for _, t, _ in textos)} chars", flush=True)
    filas = []
    for n in [int(x) for x in os.environ.get("CTX", "4096,2048").split(",")]:
        post("/api/embed", {"model": M, "input": ["x"], "keep_alive": 0})     # descargar antes de medir
        cos, toks, err, ram, ctx_real = [], [], 0, None, None
        for kind, t, guardado in textos:
            try:
                r = post("/api/embed", {"model": M, "input": [t], "truncate": False,
                                        "options": {"num_gpu": 0, "num_ctx": n}})
                cos.append((coseno(mrl(r["embeddings"][0]), guardado), kind))
                toks.append(r.get("prompt_eval_count") or 0)
                if ram is None:
                    ram, ctx_real = ram_embedder()
            except Exception as ex:
                err += 1
                print(f"  num_ctx={n} ERROR en {kind} ({len(t)} chars): {str(ex)[:120]}", flush=True)
        post("/api/embed", {"model": M, "input": ["x"], "keep_alive": 0})
        peor = min(cos) if cos else (float("nan"), "-")
        filas.append((n, ram, ctx_real, peor, max(toks) if toks else 0, err))
        print(f"num_ctx={n:5} | RAM embedder {ram if ram is None else round(ram, 2)} GB (ctx reportado {ctx_real}) "
              f"| coseno min {peor[0]:.6f} ({peor[1]}) | tokens max {max(toks) if toks else 0} | errores {err}", flush=True)
    print("\nVEREDICTO (criterio fijado antes):")
    for n, ram, ctx_real, peor, tk, err in filas:
        ok = err == 0 and peor[0] >= 0.9999
        print(f"  num_ctx={n}: {'PASA' if ok else 'NO PASA'}  (coseno min {peor[0]:.6f}, errores {err}, RAM {ram} GB)")
    print("  referencia medida antes: ctx 32768 -> 9.8 GB en RAM")


if __name__ == "__main__":
    main()
