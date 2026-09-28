"""exp #80: ¿cambio `embed_4b_num_ctx` 32768->4096 los vectores de las QUERIES en CPU?

Todas las corridas posteriores al 2026-09-14 difieren de `qonly2_dev` en las MISMAS 13 queries.
El test de adopcion de num_ctx comparo CPU 4096 vs CPU 2048 en 7 textos; nunca el payload viejo
contra el nuevo sobre queries reales. Esto lo mide. Solo lee: no toca la DB.

Brazo VIEJO = payload exacto previo a 0a0d74e: options={"num_gpu": 0} (Ollama usa ctx 32768, 9.8 GB).
Brazo NUEVO = payload actual:                  options={"num_ctx": 4096, "num_gpu": 0}.

CRITERIO (fijado antes): coseno minimo < 0.9999 -> num_ctx ES fuente del corrimiento.
                         1.000000 en todas      -> NO es num_ctx; queda el tope de W de la GPU.
OJO RAM: el brazo viejo carga 9.8 GB. Correr SOLO por la cola del cron, nunca desde la sesion.
"""
import json, math, subprocess, sys, urllib.request

SET = sys.argv[1] if len(sys.argv) > 1 else "data/eval/queries_operativas_v1.jsonl"
OUT = "data/eval/results/numctx_queries.json"
MODEL = "qwen3-embedding:4b"


def embed(text, options):
    req = urllib.request.Request(
        "http://localhost:11434/api/embed",
        data=json.dumps({"model": MODEL, "input": [text], "options": options}).encode(),
        headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=600) as r:
        return json.loads(r.read())["embeddings"][0][:1024]   # prefijo MRL: lo que usa _vector_4b_search


def cos(a, b):
    return sum(x * y for x, y in zip(a, b)) / (math.sqrt(sum(x * x for x in a)) * math.sqrt(sum(y * y for y in b)))


def descargar():
    subprocess.run(["ollama", "stop", MODEL], capture_output=True)


if __name__ == "__main__":
    qs = [json.loads(l)["query"] for l in open(SET) if l.strip()]
    descargar()
    nuevo = [embed(q, {"num_ctx": 4096, "num_gpu": 0}) for q in qs]
    nuevo2 = [embed(q, {"num_ctx": 4096, "num_gpu": 0}) for q in qs]   # control: mismo payload dos veces
    descargar()                                                        # nunca los dos ctx en RAM a la vez
    viejo = [embed(q, {"num_gpu": 0}) for q in qs]
    descargar()                                                        # devuelve los 9.8 GB
    ctrl = [cos(a, b) for a, b in zip(nuevo, nuevo2)]
    c = [cos(a, b) for a, b in zip(nuevo, viejo)]
    assert min(ctrl) > 0.999999, f"el control (mismo payload) no es identico: {min(ctrl)}"
    json.dump([{"query": q, "coseno": x} for q, x in zip(qs, c)], open(OUT, "w"), ensure_ascii=False, indent=1)
    bajo = sum(1 for x in c if x < 0.9999)
    print(f"n={len(c)}  control_min={min(ctrl):.6f}  coseno_min={min(c):.6f}  <0.9999: {bajo}/{len(c)}")
    print("VEREDICTO:", "num_ctx ES fuente del corrimiento" if bajo else "NO es num_ctx -> mirar tope de W")
