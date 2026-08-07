"""E0c: detectar queries de definición IMPOSIBLES (el corpus no define el término).

Origen: E3 + auditoría de golds (2026-08-07) mostró que 11 de las 26 fallas piden definiciones que
NO existen en el corpus — el gold apunta a un artículo donde el término solo APARECE
(ej 1160108/16 "diagrama georreferenciado de la acometida"), no donde se define.
El sistema RECHAZA correctamente y el eval lo penaliza.

Audita las 279 in_domain (no solo las fallas): una query que PASA con gold mención-only acertó por
suerte y también ensucia la métrica.

Para cada query de definición:
  1. extrae el concepto (mismo `_definition_concept` que usa el retriever)
  2. busca en los 2960 artículos si ALGUNO lo define (5 patrones)
  3. revisa si el/los GOLD lo definen o solo lo mencionan

Salida: reporte + `data/eval/queries_balanced_v2_clean.jsonl` con campo `unanswerable: true`
en las imposibles (WRITE=1). NO toca los golds; solo agrega metadata.
Las marcadas deben puntuar RECHAZO = ACIERTO (como la categoría off_corpus).

Uso:            PYTHONPATH=. venv/bin/python -m scripts.audit_unanswerable
Para escribir:  WRITE=1 PYTHONPATH=. venv/bin/python -m scripts.audit_unanswerable
"""
import json, os, re, unicodedata
from pathlib import Path
from src.storage.connection import with_connection
from src.pipelines.grounding import _normalize_art
from src.pipelines.retrieve import _definition_concept

SET = Path("data/eval/queries_balanced_v2_clean.jsonl")
WRITE = os.environ.get("WRITE") == "1"


def strip(s: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", s or "") if unicodedata.category(c) != "Mn").lower()


def def_patterns(concept: str) -> list[str]:
    """OJO (aprendido a los golpes 2026-08-07):
    - La sigla llega SIN el punto final porque `_definition_concept` lo strippea
      ('C.O.M.A.' -> 'C.O.M.A'), pero el texto dice 'C.O.M.A.: Costos anuales...'
      -> hay que permitir un punto opcional antes de los dos puntos. Sin esto se
      marcaban como IMPOSIBLES siglas que SÍ están definidas (C.O.M.A, A.V.I, V.A.T.T).
    - NO usar 'TERM es/será': matchea frases incidentales ('La Empresa Distribuidora
      SERÁ RESPONSABLE de obtener las medidas...') y produce definiciones fantasma.
    """
    c = re.escape(strip(concept))
    return [
        r'(^|[^a-z0-9])' + c + r'\.?\s*:',              # "TERM:" / "a) TERM:" / "C.O.M.A.:" / "TON  : "
        r'se entiende(?:ra)? por\s+"?' + c,             # "se entiende por TERM"
        r'se entender[aá]\s+por\s+"?' + c,
        r'se denomina(?:ra)?\s+"?' + c,                 # "se denomina TERM"
        r'definicion de\s+"?' + c,                      # titulo "Definición de V.A.T.T."
    ]


def main():
    rows = [json.loads(l) for l in SET.read_text().splitlines() if l.strip()]
    with with_connection() as conn, conn.cursor() as cur:
        cur.execute("SELECT id_norma, numero, texto FROM articulos")
        arts = [(str(n), _normalize_art(str(a)), strip(t)) for n, a, t in cur.fetchall()]
    idx = {(n, a): t for n, a, t in arts}
    print(f"articulos: {len(arts)}   queries: {len(rows)}", flush=True)

    imposibles, gold_malo, ok = [], [], 0
    for q in rows:
        if q.get("category") != "in_domain":
            continue
        c = _definition_concept(q["query"])
        if not c:
            continue
        pats = def_patterns(c)
        # 1) alguien lo define en el corpus?
        donde = [(n, a) for n, a, t in arts if any(re.search(p, t) for p in pats)]
        # 2) el gold lo define?
        golds = [(str(q["expected_norma"]), _normalize_art(str(q["expected_articulo"])))]
        for g in q.get("also_gold") or []:
            n, a = str(g).split("/", 1); golds.append((n, _normalize_art(a)))
        gold_define = any(
            any(re.search(p, idx[g]) for p in pats) for g in golds if g in idx
        )
        if not donde:
            imposibles.append((q, c))
            q["unanswerable"] = True
        elif not gold_define:
            gold_malo.append((q, c, donde[:3]))
        else:
            ok += 1

    print(f"\n=== {len(imposibles)} IMPOSIBLES (nadie define el termino en el corpus) ===", flush=True)
    for q, c in imposibles:
        print(f"  {c[:26]:26} gold={q['expected_norma']}/{q['expected_articulo']:<12} | {q['query'][:40]}", flush=True)

    print(f"\n=== {len(gold_malo)} GOLD MALO (el termino SI se define, pero en OTRO articulo) ===", flush=True)
    for q, c, donde in gold_malo:
        print(f"  {c[:24]:24} gold={q['expected_norma']}/{str(q['expected_articulo'])[:8]:8} "
              f"-> deberia ser {['/'.join(d) for d in donde]} | {q['query'][:32]}", flush=True)

    print(f"\n  sanas: {ok}   imposibles: {len(imposibles)}   gold-malo: {len(gold_malo)}", flush=True)

    if WRITE:
        SET.write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in rows) + "\n")
        print(f"\n[WRITE] {SET} actualizado con 'unanswerable' en {len(imposibles)} queries", flush=True)
    else:
        print("\n(dry-run; usar WRITE=1 para persistir el campo 'unanswerable')", flush=True)


if __name__ == "__main__":
    main()
