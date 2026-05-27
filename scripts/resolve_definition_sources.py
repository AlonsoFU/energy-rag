"""Resolve each concept's authoritative DEFINITION source (Capa 0→2).

For every concept, gather its defining articles as candidates; if the marked
definition is weak (Capa 0), try the deterministic resolver (Capa 1, high
confidence) and, failing that, the tentative LLM proposer (Capa 2, low
confidence). Writes conceptos.metadata.definition_source = {id_norma, articulo,
criterio, confianza, needs_review} — high confidence has needs_review=False,
low confidence True. Also writes an auditable YAML. Dry-run by default;
--apply writes. Idempotent (recomputes from current data each run).

Run:  PYTHONPATH=. ./venv/bin/python scripts/resolve_definition_sources.py
      PYTHONPATH=. ./venv/bin/python scripts/resolve_definition_sources.py --apply
"""
from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path

import yaml
from psycopg.rows import dict_row

from src.extraction.candidate_gather import gather_candidates
from src.extraction.definition_quality import suspect_definition
from src.extraction.definition_scoring import score_definitoriedad
from src.extraction.definition_source import resolve_definition_source
from src.extraction.definition_proposer import propose_definition_source
from src.extraction.norm_rank import derive_rank
from src.storage.connection import with_connection

REVIEW_PATH = Path("glossary/incoming/definition_source_review.yaml")
CONFIRMED_PATH = Path("glossary/confirmed_definition_sources.yaml")


def load_confirmed() -> dict[int, dict]:
    """Human-confirmed definition sources (durable, in git). Keyed by concepto_id.
    These override the resolver: written with needs_review=false and never
    recomputed, so manual curation survives every --apply run."""
    if not CONFIRMED_PATH.exists():
        return {}
    items = yaml.safe_load(CONFIRMED_PATH.read_text(encoding="utf-8")) or []
    return {int(it["concepto_id"]): it for it in items}

# Candidates come from ANY article where the concept appears (`define_termino`
# OR `cita`), not just the glossary-phrased `define_termino` edges. This is what
# makes constitutive ("la X será una persona jurídica…") and methodological
# ("el A.V.I. se determinará…") definitions reachable — they were tagged `cita`
# because they don't say "se entenderá por". The deterministic layer (Capa 1)
# still trusts ONLY `define_termino`; `cita` candidates feed the tentative
# layer (Capa 2), ranked by definitoriedad, and stay needs_review.
SQL = """
SELECT c.id AS concepto_id, c.nombre, c.definicion, c.aliases,
       a.id_norma, a.numero AS articulo, a.texto, r.tipo_relacion,
       n.tipo, n.numero AS norma_numero, n.titulo, n.fecha_publicacion
FROM conceptos c
JOIN referencias r ON r.destino_concepto_id = c.id
                  AND r.tipo_relacion IN ('define_termino', 'cita')
JOIN articulos a ON a.id = r.origen_articulo_id
JOIN normas n ON n.id_norma = a.id_norma
ORDER BY c.id, a.id_norma, a.numero
"""


def build_candidates(rows: list[dict]) -> list[dict]:
    out = []
    seen: set[tuple] = set()
    # When the SAME article carries both a `define_termino` and a `cita` edge,
    # the definitional one MUST win the dedup. Otherwise the real definition is
    # mislabeled `cita` and dropped from the trusted Capa 1 (the deterministic
    # layer only trusts `define_termino`), so a worse candidate resolves. The
    # SQL does not order by tipo_relacion, so we stable-sort `define_termino`
    # first here; nothing else is reordered.
    _prio = {"define_termino": 0, "cita": 1}
    rows = sorted(rows, key=lambda r: _prio.get(r["tipo_relacion"], 9))
    for r in rows:
        key = (str(r["id_norma"]), str(r["articulo"]))
        if key in seen:
            continue
        seen.add(key)
        rank, _ = derive_rank(r["tipo"], r["titulo"])
        # `define_termino` → curated (Capa 1 may trust); `cita` → tentative only.
        origin = "curated" if r["tipo_relacion"] == "define_termino" else "cita"
        out.append({
            "id_norma": r["id_norma"], "articulo": r["articulo"],
            "numero": r.get("norma_numero"), "titulo": r.get("titulo"),
            "rank": rank, "origin": origin,
            "fecha": r["fecha_publicacion"].isoformat() if r["fecha_publicacion"] else None,
            # `definicion` = the concept's MARKED definition (same per concept):
            # this is what is_label inspects in Capa 1, so a glossary article that
            # only labels the concept ("Comisión: CNE") routes to Capa 2, not a
            # false high-confidence resolve. `texto` = the article body, used by
            # definitoriedad scoring and shown to the proposer.
            "definicion": (r["definicion"] or "")[:2000],
            "texto": (r["texto"] or "")[:2000],
        })
    return out


def _build_store():
    """Construct the PostgresStore, mirroring src/cli.py."""
    from src.components.vectorstore import PostgresStore
    return PostgresStore()


def _build_retriever():
    """Build the real GPU-backed retriever, mirroring src/cli.py."""
    from src.components.embedder import Qwen3Embedder
    from src.components.reranker import Qwen3Reranker
    from src.pipelines.retrieve import SimpleRetriever
    store = _build_store()
    return SimpleRetriever(store, Qwen3Embedder(), Qwen3Reranker())


def _build_embed_fn():
    """Return the real embedder's `embed` (GPU) for definitoriedad scoring."""
    from src.components.embedder import Qwen3Embedder
    return Qwen3Embedder().embed


def _retrieved_candidates(retriever, cur, nombre, aliases, norma_cache, top_k=8):
    """Run retrieval for the concept name + aliases; enrich each hit with
    rank/fecha (looked up from `normas`) so it is a valid candidate. origin is
    added later by gather_candidates."""
    queries = [nombre] + [str(a) for a in (aliases or [])]
    seen = set()
    out = []
    for q in queries:
        for doc in retriever.retrieve(q, top_k=top_k):
            idn, art = str(doc.get("id_norma")), str(doc.get("articulo_numero"))
            if not idn or not art or (idn, art) in seen:
                continue
            seen.add((idn, art))
            if idn not in norma_cache:
                cur.execute("SELECT tipo, titulo, fecha_publicacion FROM normas WHERE id_norma = %s", (idn,))
                row = cur.fetchone()
                norma_cache[idn] = row
            n = norma_cache.get(idn)
            if not n:
                continue
            rank, _ = derive_rank(n["tipo"], n["titulo"])
            out.append({
                "id_norma": idn, "articulo": art, "rank": rank,
                "numero": n.get("numero"), "titulo": n.get("titulo"),
                "fecha": n["fecha_publicacion"].isoformat() if n["fecha_publicacion"] else None,
                "definicion": "", "texto": (doc.get("text") or "")[:2000],
            })
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true", help="write to DB + YAML (default dry-run)")
    ap.add_argument("--with-retrieval", action="store_true",
                    help="for unresolved concepts, also gather candidates via corpus retrieval (GPU)")
    ap.add_argument("--score", action="store_true",
                    help="rank Capa-2 candidates by semantic definitoriedad (embedder, GPU)")
    ap.add_argument("--top-k", type=int, default=8,
                    help="how many top-definitoriedad candidates feed the proposer")
    args = ap.parse_args()

    decisions: list[dict] = []
    retriever = _build_retriever() if args.with_retrieval else None
    embed_fn = _build_embed_fn() if args.score else None
    norma_cache: dict = {}
    with with_connection() as conn, conn.cursor(row_factory=dict_row) as cur:
        cur.execute(SQL)
        by_concept: dict[tuple, list[dict]] = defaultdict(list)
        meta: dict[tuple, dict] = {}
        for row in cur.fetchall():
            key = (row["concepto_id"], row["nombre"])
            by_concept[key].append(row)
            meta.setdefault(key, {"definicion": row["definicion"], "aliases": row.get("aliases") or []})

        confirmed = load_confirmed()
        for (cid, nombre), rows in by_concept.items():
            # Human-confirmed sources win and are never recomputed (durable).
            if cid in confirmed:
                cf = confirmed[cid]
                decisions.append({
                    "id": cid, "nombre": nombre, "id_norma": str(cf["id_norma"]),
                    "articulo": str(cf["articulo"]), "criterio": "confirmado_humano",
                    "confianza": "alta", "needs_review": False,
                    "fundamento": "confirmado por humano (glossary/confirmed_definition_sources.yaml)",
                    "reasons": ["confirmado"]})
                continue
            definicion = meta[(cid, nombre)]["definicion"] or ""
            suspect, reasons = suspect_definition(nombre, definicion)
            if not suspect:
                continue
            cands = build_candidates(rows)
            # Capa 1 (deterministic, high confidence) trusts ONLY define_termino.
            curated = [c for c in cands if c["origin"] == "curated"]
            res = resolve_definition_source(nombre, curated)
            if res["status"] == "resolved":
                d = {"id": cid, "nombre": nombre, "id_norma": res["id_norma"],
                     "articulo": res["articulo"], "criterio": res["criterio"],
                     "confianza": "alta", "needs_review": False,
                     "fundamento": "", "reasons": reasons}
            else:
                # Capa 2 (tentative): the full pool — define_termino + cita
                # (+ retrieval) — ranked by definitoriedad, top-K to the proposer.
                cands_for_proposer = cands
                if args.with_retrieval and retriever is not None:
                    retrieved = _retrieved_candidates(retriever, cur, nombre,
                                                       meta[(cid, nombre)].get("aliases"),
                                                       norma_cache)
                    cands_for_proposer = gather_candidates(cands, retrieved)
                if embed_fn is not None:
                    score_definitoriedad(nombre, cands_for_proposer, embed_fn)
                    cands_for_proposer = cands_for_proposer[:args.top_k]
                prop = propose_definition_source(nombre, cands_for_proposer)
                if prop.get("status") != "proposed":
                    d = {"id": cid, "nombre": nombre, "id_norma": None,
                         "articulo": None, "criterio": "ninguno",
                         "confianza": "baja", "needs_review": True,
                         "fundamento": "sin propuesta (regla no resolvió, LLM no propuso)",
                         "reasons": reasons}
                else:
                    fund = prop["fundamento"]
                    if prop.get("fundamento_warning"):
                        fund = "[fundamento_inconsistente con la norma elegida] " + fund
                    d = {"id": cid, "nombre": nombre, "id_norma": prop["id_norma"],
                         "articulo": prop["articulo"], "criterio": prop["criterio"],
                         "confianza": "baja", "needs_review": True,
                         "fundamento": fund, "reasons": reasons}
            decisions.append(d)

        applied = [d for d in decisions if d["id_norma"]]
        review = [d for d in decisions if d["needs_review"]]
        print(f"suspect concepts: {len(decisions)} | applied-mark: {len(applied)} "
              f"| needs_review: {len(review)}")
        for d in decisions:
            tag = "OK alta" if not d["needs_review"] else "REVISAR baja"
            print(f"  [{tag}] {d['nombre'][:32]:32} -> {d['id_norma']} art {d['articulo']} "
                  f"({d['criterio']}; {','.join(d['reasons'])})")

        if not args.apply:
            print("\n--dry-run: nada escrito. Usa --apply.")
            return

        for d in decisions:
            if not d["id_norma"]:
                continue
            cur.execute(
                "UPDATE conceptos SET metadata = coalesce(metadata,'{}'::jsonb) "
                "|| %(m)s::jsonb WHERE id = %(id)s",
                {"id": d["id"], "m": json.dumps({
                    "definition_source": {
                        "id_norma": d["id_norma"], "articulo": d["articulo"],
                        "criterio": d["criterio"], "confianza": d["confianza"],
                        "needs_review": d["needs_review"]},
                    "def_source_resolved": {"metodo": "capas_0_2"}})},
            )
        conn.commit()
        print(f"\nAplicado: {len(applied)} apuntadores ({len(review)} con needs_review).")

    REVIEW_PATH.parent.mkdir(parents=True, exist_ok=True)
    REVIEW_PATH.write_text(
        yaml.safe_dump(review, allow_unicode=True, sort_keys=False), encoding="utf-8")
    print(f"Escrito {len(review)} pendientes -> {REVIEW_PATH}")


if __name__ == "__main__":
    main()
