"""FASE 3.1 — registrar las preguntas REALES y si la respuesta sirvió.

Por qué existe. Los sets de evaluación de este proyecto están fabricados desde adentro: yo
escribí las preguntas mirando el corpus. Eso ya se pagó caro una vez —279 queries del set
primario usaban las mismas 3 plantillas que el regex que decían evaluar, y el eval se medía
contra sí mismo. Una pregunta que sale de alguien que necesita la respuesta trae modismos,
elipsis y supuestos que yo no puedo inventar.

Este módulo no evalúa nada. Solo guarda lo que pasó, con el veredicto de quien preguntó, para
que el set de evaluación se construya desde el uso y no desde mi imaginación.

**El veredicto es opcional y se pide UNA vez, al final.** Si se contesta con Enter queda como
`None` — sin veredicto, que es distinto de "no sirvió". Confundir esas dos cosas es la misma
falla que contar un rechazo correcto como fallo (regla #2).
"""
from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path

DESTINO = Path("data/eval/preguntas_reales.jsonl")


def registrar(pregunta: str, respuesta: str, docs: list, segundos: float,
              veredicto: bool | None = None, nota: str = "") -> None:
    """Agrega una línea. Nunca revienta la consulta: si falla el registro, se calla."""
    try:
        fuentes = []
        for d in (docs or [])[:10]:
            k = f"{(d or {}).get('id_norma')}/{(d or {}).get('articulo_numero')}"
            if k not in fuentes:
                fuentes.append(k)
        DESTINO.parent.mkdir(parents=True, exist_ok=True)
        fila = {"cuando": datetime.now().isoformat(timespec="seconds"),
                "query": pregunta,
                "respuesta": respuesta,
                "pool": fuentes,
                "secs": round(segundos, 1),
                "sirvio": veredicto,          # True / False / None = no se contestó
                "nota": nota,
                # lo llena el usuario despues, revisando el jsonl: la norma/articulo correcto.
                # sin esto la pregunta sirve para medir cobertura pero no aciertos.
                "expected_norma": None,
                "expected_articulo": None}
        with DESTINO.open("a", encoding="utf-8") as f:
            f.write(json.dumps(fila, ensure_ascii=False) + "\n")
    except Exception:
        pass


def preguntar_veredicto() -> tuple[bool | None, str]:
    """Pide el veredicto. Enter = sin veredicto (NO es 'no sirvió')."""
    if not sys.stdin.isatty():
        return None, ""
    try:
        r = input("  ¿te sirvió? [s/n, Enter para saltar]: ").strip().lower()
    except (EOFError, KeyboardInterrupt):
        return None, ""
    if r.startswith("s"):
        return True, ""
    if r.startswith("n"):
        try:
            return False, input("  ¿qué esperabas? (Enter para saltar): ").strip()
        except (EOFError, KeyboardInterrupt):
            return False, ""
    return None, ""


def resumen() -> None:
    if not DESTINO.exists():
        print("\n  Todavía no hay preguntas reales registradas.")
        print("  Se registran solas cada vez que usás:  preguntar.py \"...\"")
        return
    filas = [json.loads(l) for l in DESTINO.read_text().splitlines() if l.strip()]
    si = sum(1 for f in filas if f.get("sirvio") is True)
    no = sum(1 for f in filas if f.get("sirvio") is False)
    sin = sum(1 for f in filas if f.get("sirvio") is None)
    con_gold = sum(1 for f in filas if f.get("expected_norma"))
    print(f"\n=== {len(filas)} preguntas reales ===")
    print(f"  sirvió: {si}   no sirvió: {no}   sin veredicto: {sin}")
    print(f"  con gold anotado: {con_gold}  (hace falta para medir aciertos)")
    if filas:
        print(f"  tiempo mediana: {sorted(f['secs'] for f in filas)[len(filas) // 2]:.0f} s")
    for f in filas:
        if f.get("sirvio") is False:
            print(f"  ✗ {f['query'][:60]}" + (f"  — {f['nota'][:40]}" if f.get("nota") else ""))
    print(f"\n  archivo: {DESTINO}")
