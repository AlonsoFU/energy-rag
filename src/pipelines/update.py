"""BCN incremental updater.

Diff phase: implemented and tested. Reads `descargas_estado` and compares against
an injected BCN index list, returning nuevas / outdated / desaparecidas.

Fetch phase: TODO. The actual scrape of the BCN catalog and download of new norms
is not yet wired up; it should reuse the existing scripts/DOWNLOAD_ALL_NORMS.py
logic. For now, run_update either receives an explicit bcn_index (tests, future
scheduler), or skips when called without one.
"""
from psycopg.rows import dict_row
from src.storage.connection import with_connection


def diff_against_db(bcn_index: list[dict]) -> dict[str, list[str]]:
    """Compare a BCN index list vs descargas_estado.

    bcn_index: list of {id_norma, hash}.
    Returns: {'nuevas', 'outdated', 'desaparecidas'} — each a list of id_norma.
    """
    incoming_hashes = {item["id_norma"]: item.get("hash") for item in bcn_index}

    with with_connection() as conn, conn.cursor(row_factory=dict_row) as cur:
        cur.execute("SELECT id_norma, bcn_hash, estado FROM descargas_estado")
        existing = {r["id_norma"]: r for r in cur.fetchall()}

    nuevas = [iid for iid in incoming_hashes if iid not in existing]
    outdated = [
        iid for iid, h in incoming_hashes.items()
        if iid in existing
        and existing[iid]["bcn_hash"] != h
        and existing[iid]["estado"] == "downloaded"
    ]
    desaparecidas = [iid for iid in existing if iid not in incoming_hashes]
    return {"nuevas": nuevas, "outdated": outdated, "desaparecidas": desaparecidas}


def run_update(dry_run: bool = False, bcn_index: list[dict] | None = None) -> dict:
    """Stage 1 (diff). Stage 2 (fetch + reingest) is TODO.

    bcn_index: when not provided, the function is a no-op and prints a TODO note.
    Tests inject this list directly. Future: a separate scraper module produces it.
    """
    if bcn_index is None:
        print("[update] No bcn_index provided. Fetch from biblioteca.bcn.cl is not yet wired.")
        print("[update] Provide bcn_index=[{'id_norma': ..., 'hash': ...}, ...] to run the diff.")
        return {"status": "no-fetch-implemented"}

    diff = diff_against_db(bcn_index)
    print(
        f"[update] nuevas={len(diff['nuevas'])} "
        f"outdated={len(diff['outdated'])} "
        f"desaparecidas={len(diff['desaparecidas'])}"
    )
    if dry_run:
        return diff

    print("[update] Real download + re-ingest of delta is TODO (see Phase 11 Task 41 notes).")
    return {"status": "diff-only", **diff}
