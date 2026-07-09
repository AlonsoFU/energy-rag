"""QA de CHUNKING — chequeos que el sweep nunca hizo.

El sweep midió SOLO retrieval (gold∈topN). Nunca verificó que los chunks estén
sanos: ¿se pierde texto?, ¿quedan huérfanos?, ¿se corta una definición a la mitad?
Esas patologías no se ven en el screen pero SÍ envenenan la generación (distractores).

Corre sobre cada chunker de exp_chunk_sweep.py leyendo articulos.texto. Sin GPU,
sin embeddings.

Métricas por chunker:
  n_chunks      total de fragmentos
  cobertura     Σ chars(chunks) / chars(artículo). <1 = texto PERDIDO. >1 = redundancia (solape).
  perdida_arts  artículos con cobertura <0.99 (texto realmente perdido)
  huérfanos     chunks <50 chars (ruido) y >3000 chars (mega-chunk, señal diluida)
  tamaños       p10 / p50 / p90 / max
  start_lower   % chunks que empiezan en minúscula → cortado a mitad de frase
  no_end_punct  % chunks que no terminan en .;:!?) → cortado a mitad de frase
  defs_cortadas % de definiciones "TÉRMINO: ..." que NO aparecen íntegras en ningún chunk

Uso: ./venv-gpu/bin/python -m scripts.qa_chunking
"""
import re
import statistics as st
from src.storage.connection import with_connection
from psycopg.rows import dict_row
from scripts.exp_chunk_sweep import CHUNKERS

TINY, HUGE = 50, 3000
_WS = re.compile(r"\s+")
# una definición de glosario: marcador + TÉRMINO + ':' + definición
_DEF = re.compile(r"(?:^|\n|;)\s*(?:[a-zñ]{1,2}|\d{1,2})[.)]\s+([^:\n]{2,90}):\s*([^\n;]{20,})")
_ENDP = tuple(".;:!?)”\"'")
DEF_PROBE = 60  # chars de la definición usados como sonda
# marcador de enumeración AL INICIO de un chunk ("a.", "1)", "1°", "III.", "§ 4").
# Hay que quitarlo antes de juzgar "empieza en minúscula": el chunk 'a. TÉRMINO...'
# arranca con 'a' minúscula por el MARCADOR, no por un corte a mitad de frase.
_LEAD = re.compile(r"^(?:§\s*\d+|(?:[a-zñ]{1,2}|\d{1,2}[°º]?|[IVXLC]{1,4})[.)\-])\s*")


def norm(s):
    return _WS.sub(" ", s).strip()


def load_articulos():
    with with_connection() as c, c.cursor(row_factory=dict_row) as cur:
        cur.execute("SELECT id, id_norma, numero, titulo, texto FROM articulos "
                    "WHERE texto IS NOT NULL AND texto <> ''")
        return cur.fetchall()


def def_probes(texto):
    """Sondas: 'TÉRMINO: primeros N chars de la definición'. Si una sonda no aparece
    contigua en ningún chunk → esa definición fue cortada por un límite."""
    out = []
    for m in _DEF.finditer(texto):
        term, d = m.group(1).strip(), m.group(2).strip()
        out.append(norm(f"{term}: {d[:DEF_PROBE]}"))
    return out


def qa_one(name, ck, arts):
    sizes, n_tiny, n_huge = [], 0, 0
    start_lower, no_end = 0, 0
    cov_num, cov_den = 0, 0
    lost_arts = []
    defs_tot, defs_cut = 0, 0
    for a in arts:
        chunks = [c for c in ck(a) if c and c.strip()]
        art_len = len(norm(a["texto"]))
        ch_len = sum(len(norm(c)) for c in chunks)
        cov_num += ch_len; cov_den += art_len
        if art_len and ch_len / art_len < 0.99:
            lost_arts.append((a["id_norma"], a["numero"], round(ch_len / art_len, 3)))
        nchunks = [norm(c) for c in chunks]
        for c in nchunks:
            L = len(c)
            sizes.append(L)
            n_tiny += L < TINY
            n_huge += L > HUGE
            body = _LEAD.sub("", c)  # quita el marcador de enumeración inicial
            if body and body[0].islower():
                start_lower += 1
            if c and not c.endswith(_ENDP):
                no_end += 1
        # boundary integrity sobre definiciones
        probes = def_probes(a["texto"])
        if probes:
            blob = nchunks  # buscar sonda contigua dentro de UN chunk
            for p in probes:
                defs_tot += 1
                if not any(p in c for c in blob):
                    defs_cut += 1
    n = len(sizes) or 1
    q = sorted(sizes)
    def pct(p):
        return q[min(len(q) - 1, int(len(q) * p))] if q else 0
    return {
        "n_chunks": len(sizes),
        "cobertura": round(cov_num / cov_den, 4) if cov_den else 0,
        "perdida_arts": len(lost_arts),
        "tiny": n_tiny, "huge": n_huge,
        "p10": pct(.10), "p50": pct(.50), "p90": pct(.90), "max": max(q) if q else 0,
        "start_lower_pct": round(100 * start_lower / n, 1),
        "no_end_punct_pct": round(100 * no_end / n, 1),
        "defs_tot": defs_tot, "defs_cut": defs_cut,
        "defs_cut_pct": round(100 * defs_cut / defs_tot, 1) if defs_tot else 0.0,
        "_lost": lost_arts[:5],
    }


def main():
    arts = load_articulos()
    print(f"articulos={len(arts)}\n")
    order = ["whole", "glossary", "inciso", "inciso_robust", "inciso_maxsplit",
             "slide1000_200", "slide500_100", "recursive"]
    order = [o for o in order if o in CHUNKERS]
    res = {}
    for nm in order:
        res[nm] = qa_one(nm, CHUNKERS[nm], arts)
        print(f"  {nm} ok", flush=True)
    print("\n=== QA CHUNKING ===")
    hdr = (f"{'chunker':16s} {'chunks':>7s} {'cobert':>7s} {'perdi':>6s} {'tiny':>6s} {'huge':>5s} "
           f"{'p10':>5s} {'p50':>5s} {'p90':>6s} {'max':>6s} {'startLo%':>8s} {'noEnd%':>7s} {'defsCut%':>8s}")
    print(hdr)
    for nm in order:
        r = res[nm]
        print(f"{nm:16s} {r['n_chunks']:>7d} {r['cobertura']:>7.3f} {r['perdida_arts']:>6d} "
              f"{r['tiny']:>6d} {r['huge']:>5d} {r['p10']:>5d} {r['p50']:>5d} {r['p90']:>6d} {r['max']:>6d} "
              f"{r['start_lower_pct']:>8.1f} {r['no_end_punct_pct']:>7.1f} {r['defs_cut_pct']:>8.1f}")
    print("\nleyenda: cobert<1 = texto PERDIDO · cobert>1 = redundancia(solape) · "
          f"tiny=<{TINY}c · huge=>{HUGE}c · defsCut% = definiciones partidas por un límite")
    for nm in order:
        if res[nm]["_lost"]:
            print(f"\n{nm}: ejemplos con pérdida >1%: {res[nm]['_lost']}")


if __name__ == "__main__":
    main()
