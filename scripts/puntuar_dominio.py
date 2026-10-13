"""T14 — scorer de precision de dominio (H1-CA-37, H1-CA-38).

Dado el conjunto etiquetado y los puntajes de una corrida, entrega por particion (`dev`,
`heldout`) la precision de la clase "en dominio" y las normas en dominio que cayeron fuera.

COMO SE PUNTUA CADA CASO (declarado antes del codigo):
  - Clasificada en dominio = el puntaje trae `clase == "en_dominio"`. Es correcta si la
    etiqueta tambien es `en_dominio`. precision = correctas / clasificadas en dominio
    (None si el denominador es 0).
  - `dudosa` no cuenta como acierto ni como error en la precision; se informa aparte
    (`dudosas`), sea cual sea la etiqueta.
  - Sin puntaje (`clase` null, o norma etiquetada que no aparece en los puntajes) se excluye
    de la precision y se cuenta en `sin_puntaje`.
  - Una norma con puntaje que no esta en el etiquetado se ignora y se cuenta en
    `no_etiquetadas` (a nivel raiz del resultado).
  - `en_dominio_caidas_fuera` = `id_norma` etiquetados `en_dominio` y clasificados
    `fuera_de_dominio`.
  - El script informa; no decide si se cumple el umbral. Sale con 0 si pudo calcular.

  PYTHONPATH=. venv/bin/python -m scripts.puntuar_dominio \\
      --etiquetado data/eval/dominio/etiquetado.jsonl --puntajes puntajes.jsonl --salida out.json
"""
import argparse
import json
import sys
from pathlib import Path


def _leer_jsonl(ruta) -> list[dict]:
    filas = []
    for linea in Path(ruta).read_text(encoding="utf-8").splitlines():
        if linea.strip():
            filas.append(json.loads(linea))
    return filas


def puntuar(etiquetado: list[dict], puntajes: list[dict]) -> dict:
    """Calcula la precision de dominio por particion. Funcion pura."""
    por_id = {str(p["id_norma"]): p for p in puntajes}
    ids_etiquetados = {str(e["id_norma"]) for e in etiquetado}
    resultado: dict = {
        "particiones": {},
        "no_etiquetadas": sum(1 for i in por_id if i not in ids_etiquetados),
        "detalle": [],
    }
    for e in etiquetado:
        idn = str(e["id_norma"])
        p = por_id.get(idn)
        part = e["particion"]
        r = resultado["particiones"].setdefault(part, {
            "clasificadas_en_dominio": 0, "en_dominio_correctas": 0, "precision": None,
            "en_dominio_caidas_fuera": [], "dudosas": 0, "sin_puntaje": 0, "total": 0,
        })
        clase = p.get("clase") if p else None
        r["total"] += 1
        if clase is None:
            r["sin_puntaje"] += 1
        elif clase == "dudosa":
            r["dudosas"] += 1
        elif clase == "en_dominio":
            r["clasificadas_en_dominio"] += 1
            if e["etiqueta"] == "en_dominio":
                r["en_dominio_correctas"] += 1
        elif clase == "fuera_de_dominio" and e["etiqueta"] == "en_dominio":
            r["en_dominio_caidas_fuera"].append(idn)
        resultado["detalle"].append({
            "id_norma": idn, "particion": part, "etiqueta": e["etiqueta"],
            "puntaje": p.get("puntaje") if p else None, "clase": clase,
        })
    for r in resultado["particiones"].values():
        if r["clasificadas_en_dominio"]:
            r["precision"] = r["en_dominio_correctas"] / r["clasificadas_en_dominio"]
    return resultado


def _imprimir(resultado: dict) -> None:
    print(f"{'particion':<10}{'clasif.':>8}{'correctas':>10}{'precision':>10}"
          f"{'caidas':>8}{'dudosas':>8}{'sin_punt.':>10}{'total':>7}")
    for part, r in sorted(resultado["particiones"].items()):
        prec = "n/d" if r["precision"] is None else f"{r['precision']:.3f}"
        print(f"{part:<10}{r['clasificadas_en_dominio']:>8}{r['en_dominio_correctas']:>10}"
              f"{prec:>10}{len(r['en_dominio_caidas_fuera']):>8}{r['dudosas']:>8}"
              f"{r['sin_puntaje']:>10}{r['total']:>7}")
    print(f"no etiquetadas (ignoradas): {resultado['no_etiquetadas']}")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--etiquetado", required=True)
    ap.add_argument("--puntajes", required=True)
    ap.add_argument("--salida", required=True)
    args = ap.parse_args(argv)
    resultado = puntuar(_leer_jsonl(args.etiquetado), _leer_jsonl(args.puntajes))
    _imprimir(resultado)
    Path(args.salida).write_text(
        json.dumps(resultado, ensure_ascii=False, indent=2), encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
