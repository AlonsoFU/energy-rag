"""Migrate JSON-stored normas (data/normas_completas/) into Postgres.

Loads normas + articulos + conceptos. No embeddings/refs — those come later
(Task 24+).

The JSON files under ``data/normas_completas/{decretos,leyes,dfl,resoluciones,otros}``
are produced by the legacy scrape pipeline; their schema is::

    {
      "id_norma": "<numeric id>",
      "tipo": "DECRETO" | "LEY" | ...,
      "numero": "<num>",
      "titulo": "<TITLE>",
      "fecha_publicacion": "YYYY-MM-DD" | "" | null,
      "organismo": "<org>" | "" | null,
      "texto_completo": "<full body>",
      ... extra metadata fields ...
    }

Some files have empty/missing required fields (``tipo``/``numero``/``titulo``).
Those rows would violate the NOT NULL columns on the ``normas`` table and are
skipped with a warning.
"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

from src.components.vectorstore import PostgresStore
from src.core.models import Articulo, Concepto, Norma
from src.pipelines.classification import classify_norma
from src.pipelines.concept_extraction import extract_concepts_from_text
from src.pipelines.date_extraction import extract_fecha_publicacion


SUBDIRS = ("decretos", "leyes", "dfl", "resoluciones", "otros")

_REQUIRED_FIELDS = ("id_norma", "tipo", "numero", "titulo")
_NORMA_CORE_KEYS = {
    "id_norma",
    "tipo",
    "numero",
    "titulo",
    "fecha_publicacion",
    "organismo",
    "texto_completo",
}


def load_norma_jsons(data_dir: Path) -> list[dict]:
    """Load every ``*.json`` file under the known subdirs of ``data_dir``."""
    out: list[dict] = []
    for sub in SUBDIRS:
        d = data_dir / sub
        if not d.exists():
            continue
        for jf in sorted(d.glob("*.json")):
            try:
                with open(jf, encoding="utf-8") as f:
                    out.append(json.load(f))
            except (json.JSONDecodeError, OSError) as e:
                print(f"[migrate] WARN: failed to load {jf}: {e}")
    return out


def _has_required_fields(d: dict) -> bool:
    return all(d.get(k) for k in _REQUIRED_FIELDS)


def to_norma(data: dict) -> Norma:
    """Convert a raw JSON dict into a :class:`Norma` pydantic model."""
    fecha = extract_fecha_publicacion(data)
    organismo = data.get("organismo") or None
    return Norma(
        id_norma=str(data["id_norma"]),
        tipo=data["tipo"],
        numero=str(data["numero"]),
        titulo=data["titulo"],
        fecha_publicacion=fecha,
        organismo=organismo,
        clase=classify_norma(data["titulo"]),
        texto_completo=data.get("texto_completo"),
        metadata={k: v for k, v in data.items() if k not in _NORMA_CORE_KEYS},
    )


# Article heading detector. Real Chilean legal text uses many forms:
#   numeric:    "Artículo 5°.-", "Artículo 5º.-", "Artículo 5 bis.-",
#               "Artículo 5° A.-"
#   word form:  "Artículo primero.-", "Artículo decimotercero.-"
#   transit.:   "Artículo primero transitorio.-", "Artículo 5° transitorio.-"
# Lines may start with non-breaking spaces (\xa0). The "." or "-" separator
# is required to avoid matching cross-references like "Art. 5° del DFL 4".
_WORD_ORDINALS = (
    r"primero|segundo|tercero|cuarto|quinto|sexto|s[eé]ptimo|octavo|noveno|"
    r"d[eé]cimo|und[eé]cimo|duod[eé]cimo|"
    r"decimo(?:primero|segundo|tercero|cuarto|quinto|sexto|s[eé]ptimo|octavo|noveno)|"
    r"vig[eé]simo(?:primero|segundo|tercero|cuarto|quinto)?"
)
_HEAD_PATTERN = (
    r"(?im)"
    r"(?:^|\n)[\s\xa0]*"
    r"(?:art[íi]culo[s]?|art\.)"
    r"[\s\xa0]+"
    r"(?P<num>"
        r"\d+\s*[°º]?(?:\s+(?:bis|ter|quater|quinquies))?(?:\s+[A-Z])?"
        r"|"
        rf"(?:{_WORD_ORDINALS})"
    r")"
    r"(?P<trans>\s+transitorio)?"
    r"\s*[\.\-]"
)
_ART_HEAD = re.compile(_HEAD_PATTERN)


def _normalize_numero(raw: str, has_transitorio: bool) -> str:
    """Collapse whitespace, lowercase suffix words, optionally add 'transitorio'."""
    n = re.sub(r"\s+", " ", raw).strip()
    n = re.sub(r"\b(BIS|TER|QUATER|QUINQUIES)\b", lambda m: m.group(1).lower(), n)
    if has_transitorio:
        n = f"{n} transitorio"
    return n


def split_into_articulos(norma_data: dict) -> list[Articulo]:
    """Split ``texto_completo`` by every detected article heading.

    Captures numeric and word-ordinal forms plus optional ``bis``/``ter`` and
    ``transitorio`` suffixes. Each article body runs from its heading to the
    next heading (or end of text). Duplicate article numbers within the same
    norma are skipped (UNIQUE constraint would reject them anyway).
    """
    texto = norma_data.get("texto_completo", "") or ""
    if not texto.strip():
        return []
    matches = list(_ART_HEAD.finditer(texto))
    if not matches:
        return []
    out: list[Articulo] = []
    seen_numeros: set[str] = set()
    for i, m in enumerate(matches):
        numero = _normalize_numero(m.group("num"), bool(m.group("trans")))
        if numero in seen_numeros:
            continue
        seen_numeros.add(numero)
        body_start = m.start()
        body_end = matches[i + 1].start() if i + 1 < len(matches) else len(texto)
        body = texto[body_start:body_end].strip()
        out.append(
            Articulo(
                id_norma=str(norma_data["id_norma"]),
                numero=numero,
                texto=body,
                orden=len(out),
            )
        )
    return out


def run_migration(
    data_dir: Path | str = "data/normas_completas",
    dry_run: bool = False,
) -> dict:
    """Walk ``data_dir`` and upsert normas/articulos/conceptos into Postgres.

    When ``dry_run`` is True nothing is written; the function only counts what
    *would* be persisted. Returns a stats dict with the counts.
    """
    data_dir = Path(data_dir)
    store = None if dry_run else PostgresStore()
    raw = load_norma_jsons(data_dir)
    stats = {
        "normas_processed": 0,
        "normas_skipped": 0,
        "articulos_processed": 0,
        "conceptos_processed": 0,
    }

    seen_concepto_names: set[str] = set()
    for d in raw:
        if not _has_required_fields(d):
            stats["normas_skipped"] += 1
            print(
                "[migrate] WARN: skipping norma with missing required field(s): "
                f"id_norma={d.get('id_norma')!r}"
            )
            continue

        n = to_norma(d)
        if not dry_run:
            store.upsert_norma(n)
        stats["normas_processed"] += 1

        for a in split_into_articulos(d):
            if not dry_run:
                store.upsert_articulo(a)
            stats["articulos_processed"] += 1

        for c in extract_concepts_from_text(d.get("texto_completo", "") or ""):
            nombre = c["nombre"]
            if nombre in seen_concepto_names:
                continue
            seen_concepto_names.add(nombre)
            if not dry_run:
                store.upsert_concepto(
                    Concepto(nombre=nombre, definicion=c["definicion"])
                )
            stats["conceptos_processed"] += 1

    print(f"[migrate] stats: {stats}")
    return stats


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--data-dir", default="data/normas_completas")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    run_migration(args.data_dir, args.dry_run)


if __name__ == "__main__":
    main()
