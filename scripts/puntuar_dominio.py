"""T14 — scorer de precision de dominio (H1-CA-37, H1-CA-38).

Dado el conjunto etiquetado y los puntajes de una corrida, entrega por particion (`dev`,
`heldout`) la precision de la clase "en dominio" y las normas en dominio que cayeron fuera.

VALIDACION (estricta, antes de puntuar). `puntuar` lanza `ValueError` si hay cualquiera de:
  - `id_norma` duplicado en el etiquetado o en los puntajes;
  - `etiqueta` distinta de `en_dominio` / `fuera_de_dominio`;
  - `clase` que no sea null ni `en_dominio` / `dudosa` / `fuera_de_dominio`;
  - `particion` distinta de `dev` / `heldout`;
  - falta de una clave obligatoria (etiquetado: `id_norma`, `etiqueta`, `particion`;
    puntajes: `id_norma`, `clase`).
  El mensaje nombra el archivo logico (etiquetado o puntajes), el `id_norma` y el valor
  ofensivo, y junta TODOS los problemas en un solo error. Los `id_norma` se comparan como
  texto: `1` y `"1"` son el mismo id (y por tanto duplicado si aparecen ambos).

COMO SE PUNTUA CADA CASO (cada norma etiquetada cae en exactamente una categoria,
segun su `clase`; el `puntaje` numerico no interviene):
  - `clase == "en_dominio"`: clasificada en dominio. Es correcta si la etiqueta tambien es
    `en_dominio`. precision = correctas / clasificadas en dominio (None si el denominador
    es 0).
  - `clase == "dudosa"`: no cuenta como acierto ni como error en la precision; se informa
    aparte (`dudosas`), sea cual sea la etiqueta.
  - `clase` null, o norma etiquetada que no aparece en los puntajes: se excluye de la
    precision y se cuenta en `sin_puntaje`.
  - `clase == "fuera_de_dominio"`: si la etiqueta es `en_dominio`, va a
    `en_dominio_caidas_fuera` (lista de `id_norma`); si la etiqueta es `fuera_de_dominio`,
    cuenta en `fuera_correctas`.
  - Clase no nula con `puntaje` null: se puntua segun la clase (el puntaje se ignora).
  - Una norma con puntaje que no esta en el etiquetado se ignora y se cuenta en
    `no_etiquetadas` (a nivel raiz del resultado).
  - Identidad de reconciliacion, por particion:
      total == clasificadas_en_dominio + dudosas + sin_puntaje
               + fuera_correctas + len(en_dominio_caidas_fuera)
  - El script informa; no decide si se cumple el umbral. Sale con 0 si pudo calcular y con
    2 si la entrada es invalida (JSON malformado o validacion fallida), sin escribir salida.

  PYTHONPATH=. venv/bin/python -m scripts.puntuar_dominio \\
      --etiquetado data/eval/dominio/etiquetado.jsonl --puntajes puntajes.jsonl --salida out.json
"""
import argparse
import json
import sys
from pathlib import Path

ETIQUETAS = ("en_dominio", "fuera_de_dominio")
CLASES = ("en_dominio", "dudosa", "fuera_de_dominio")
PARTICIONES = ("dev", "heldout")


def _leer_jsonl(ruta, nombre: str) -> list[dict]:
    """Lee un JSONL; ante una linea que no es JSON lanza ValueError con el numero de linea."""
    filas = []
    for n, linea in enumerate(Path(ruta).read_text(encoding="utf-8").splitlines(), start=1):
        if not linea.strip():
            continue
        try:
            filas.append(json.loads(linea))
        except json.JSONDecodeError as exc:
            raise ValueError(f"{nombre}: linea {n} no es JSON valido ({exc.msg})") from exc
    return filas


def _validar(etiquetado: list[dict], puntajes: list[dict]) -> None:
    """Junta todos los problemas de entrada y lanza un unico ValueError."""
    problemas: list[str] = []

    def revisar(filas, nombre, obligatorias, enumerados):
        vistos: set[str] = set()
        for pos, f in enumerate(filas, start=1):
            if not isinstance(f, dict):
                problemas.append(f"{nombre}: fila {pos} no es un objeto ({f!r})")
                continue
            faltan = [k for k in obligatorias if k not in f]
            idn = str(f["id_norma"]) if f.get("id_norma") is not None else f"<fila {pos}>"
            for k in faltan:
                problemas.append(f"{nombre}: id_norma {idn}: falta la clave {k!r}")
            if "id_norma" in f and f["id_norma"] is None:
                problemas.append(f"{nombre}: fila {pos}: id_norma es null")
            elif "id_norma" in f:
                if idn in vistos:
                    problemas.append(f"{nombre}: id_norma {idn}: duplicado")
                vistos.add(idn)
            for clave, validos, admite_null in enumerados:
                if clave in f:
                    v = f[clave]
                    if not (v is None and admite_null) and v not in validos:
                        problemas.append(
                            f"{nombre}: id_norma {idn}: {clave} invalida {v!r} "
                            f"(validos: {', '.join(validos)})")

    revisar(etiquetado, "etiquetado", ("id_norma", "etiqueta", "particion"),
            (("etiqueta", ETIQUETAS, False), ("particion", PARTICIONES, False)))
    revisar(puntajes, "puntajes", ("id_norma", "clase"), (("clase", CLASES, True),))
    if problemas:
        raise ValueError("entrada invalida:\n  " + "\n  ".join(problemas))


def puntuar(etiquetado: list[dict], puntajes: list[dict]) -> dict:
    """Calcula la precision de dominio por particion. Valida antes; funcion pura."""
    _validar(etiquetado, puntajes)
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
            "en_dominio_caidas_fuera": [], "fuera_correctas": 0,
            "dudosas": 0, "sin_puntaje": 0, "total": 0,
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
        elif clase == "fuera_de_dominio":
            if e["etiqueta"] == "en_dominio":
                r["en_dominio_caidas_fuera"].append(idn)
            else:
                r["fuera_correctas"] += 1
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
          f"{'caidas':>8}{'fuera_ok':>9}{'dudosas':>8}{'sin_punt.':>10}{'total':>7}")
    for part, r in sorted(resultado["particiones"].items()):
        prec = "n/d" if r["precision"] is None else f"{r['precision']:.3f}"
        print(f"{part:<10}{r['clasificadas_en_dominio']:>8}{r['en_dominio_correctas']:>10}"
              f"{prec:>10}{len(r['en_dominio_caidas_fuera']):>8}{r['fuera_correctas']:>9}"
              f"{r['dudosas']:>8}{r['sin_puntaje']:>10}{r['total']:>7}")
    print(f"no etiquetadas (ignoradas): {resultado['no_etiquetadas']}")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--etiquetado", required=True)
    ap.add_argument("--puntajes", required=True)
    ap.add_argument("--salida", required=True)
    args = ap.parse_args(argv)
    try:
        resultado = puntuar(_leer_jsonl(args.etiquetado, "etiquetado"),
                            _leer_jsonl(args.puntajes, "puntajes"))
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    _imprimir(resultado)
    Path(args.salida).write_text(
        json.dumps(resultado, ensure_ascii=False, indent=2), encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
