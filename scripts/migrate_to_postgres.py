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
from datetime import datetime
from pathlib import Path

from src.components.vectorstore import PostgresStore
from src.core.models import Articulo, Concepto, Norma
from src.pipelines.classification import classify_norma
from src.pipelines.concept_extraction import extract_concepts_from_text


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
    fp = data.get("fecha_publicacion")
    fecha = None
    if fp:
        try:
            fecha = datetime.strptime(fp, "%Y-%m-%d").date()
        except ValueError:
            fecha = None
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


# Match an "Artículo N°..." heading. Real-world JSON uses both the masculine
# ordinal indicator "º" and the degree sign "°" interchangeably, and the
# heading may be preceded by non-breaking whitespace. We split on a heading
# that sits at the start of a line *or* after whitespace following a newline.
_ART_HEAD = re.compile(
    r"(?m)(?:^|\n)[\s ]*(?=Art[íi]culo\s+\d+\s*[°º]?[\s:.\-])",
)
_ART_NUM = re.compile(
    r"^[\s ]*Art[íi]culo\s+(\d+(?:\s*[°º])?[a-z]?(?:\s+(?:bis|ter|quater))?)",
    re.IGNORECASE,
)


def split_into_articulos(norma_data: dict) -> list[Articulo]:
    """Split ``texto_completo`` by ``Artículo N°`` headings.

    The split is deliberately simple — anything before the first heading is
    discarded (preamble / "Vistos") and each subsequent chunk becomes one
    :class:`Articulo` keyed by the article number captured from the heading.
    Duplicate article numbers within the same norma are dropped (the table
    has UNIQUE(id_norma, numero)).
    """
    texto = norma_data.get("texto_completo", "") or ""
    if not texto.strip():
        return []
    chunks = _ART_HEAD.split(texto)
    out: list[Articulo] = []
    seen_numeros: set[str] = set()
    orden = 0
    for ch in chunks:
        m = _ART_NUM.match(ch)
        if not m:
            continue
        numero = re.sub(r"\s+", " ", m.group(1)).strip()
        if numero in seen_numeros:
            # The same article number appears twice (e.g. cited in body and
            # then defined). Keep the first occurrence; the unique constraint
            # would reject duplicates anyway.
            continue
        seen_numeros.add(numero)
        out.append(
            Articulo(
                id_norma=str(norma_data["id_norma"]),
                numero=numero,
                texto=ch.strip(),
                orden=orden,
            )
        )
        orden += 1
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
