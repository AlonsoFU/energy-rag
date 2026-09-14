"""Diagnostico liviano del 17 %: SOLO el paso de extraccion de quote-first sobre el glosario.

El diagnostico completo (`exp_diag_quote_first`) se corto por falta de RAM al cargar buscador,
embedder y reranker. Alcanzo a registrar 1 caso ("como se define Mora"): el modelo copio las
frases pero las etiqueto con un articulo que NO estaba en los docs, y el verificador las
rechazo todas.

Esto aisla los 10 casos restantes, que citan el glosario Art. 13 de 250604: le da al extractor
ESE articulo como unico doc, llama a `_quote_first` real (con think=True, como produccion) y
clasifica por que se rechaza cada linea. Sin retrieval: casi no usa RAM.
Caveat: en produccion el extractor ve ~8 docs; aca ve uno solo. Si aca verifica bien, el
problema esta en la mezcla de docs; si falla igual, esta en el glosario o en el extractor.

  env PYTHONPATH=. SET=<jsonl> venv/bin/python -m scripts.exp_diag_glosario
"""
import json, os, re
from src.core import config as cfg
from src.components.llm import get_llm_provider
from src.pipelines.generate import _quote_first, _strip_think_block
from src.pipelines.grounding import extract_citations, _normalize_art
from src.storage.connection import with_connection

MODEL = "ollama/qwen3:30b-a3b"


def norm(t):
    return re.sub(r"\s+", " ", t or "").strip().lower()


def motivo(line, idx):
    cits = extract_citations(line)
    if len(cits) != 1 or "]" not in line:
        return f"RECHAZO: {len(cits)} citas en la linea"
    nid, art = cits[0]
    t = idx.get((str(nid), _normalize_art(str(art))))
    if t is None:
        return f"RECHAZO: etiqueta Art. {art} de {nid}, que NO es el doc dado"
    q = norm(line[line.rfind("]") + 1:].strip().strip('«»"“”\' '))
    if len(q) < 30:
        return f"RECHAZO: cita corta ({len(q)} chars)"
    if q in t:
        return "OK"
    lo, hi = 0, len(q)
    while lo < hi:
        mid = (lo + hi + 1) // 2
        if q[:mid] in t:
            lo = mid
        else:
            hi = mid - 1
    pos = t.find(q[:lo]) if lo else -1
    return (f"RECHAZO: no es subcadena, calza {lo}/{len(q)} | cita sigue {q[lo:lo+40]!r}"
            f" | articulo sigue {t[pos+lo:pos+lo+40]!r}" if pos >= 0 else f"RECHAZO: ni el inicio calza")


def main():
    with with_connection() as c, c.cursor() as cur:
        cur.execute("""SELECT numero, texto FROM articulos WHERE id_norma='250604'
                       AND replace(replace(numero,'°',''),'º','')='13'
                       AND (metadata->>'duplicado_de') IS NULL AND (metadata->>'fantasma') IS NULL
                       ORDER BY length(texto) DESC LIMIT 1""")
        numero, texto = cur.fetchone()
    docs = [{"id_norma": "250604", "articulo_numero": numero, "articulo_text": texto}]
    idx = {("250604", _normalize_art(numero)): norm(texto)}
    cfg.settings.ollama_think = True          # produccion: answer_think prende think antes de extraer
    llm = get_llm_provider()
    filas = [json.loads(l) for l in open(os.environ["SET"]) if l.strip()]
    filas = [f for f in filas if str(f.get("expected_norma")) == "250604"
             and _normalize_art(str(f.get("expected_articulo"))) == "13"]
    print(f"glosario Art. {numero} de 250604: {len(texto)} chars | preguntas: {len(filas)} | "
          f"tope={cfg.settings.answer_quote_max}", flush=True)
    for f in filas:
        qs, resp = _quote_first(f["query"], docs, llm, MODEL, cfg.settings.answer_quote_max)
        crudo = _strip_think_block(resp.text)
        print(f"\n=== {f['query']} | verificadas {len(qs)}", flush=True)
        lineas = [l for l in crudo.splitlines() if l.strip()]
        if not lineas:
            print("  (el extractor no devolvio nada)", flush=True)
        for l in lineas:
            print(f"  {motivo(l, idx)}  <<  {l[:110]}", flush=True)


if __name__ == "__main__":
    main()
