"""M2: extrae fragmentos '1 definicion = 1 fragmento' de articulos-glosario.
Patron: articulos con 'se entender[ae] por:' + items 'a) Termino: def', 'b) ...'.
DRY por defecto (solo reporta cobertura). WRITE=1 crea tabla fragmentos_definicion + embeddings.

Uso dry:   PYTHONPATH=. venv/bin/python -m scripts.build_def_fragments
Uso write: PYTHONPATH=. WRITE=1 BGE_DEVICE=cuda venv/bin/python -m scripts.build_def_fragments
"""
import os, re, json
from src.storage.connection import with_connection

# item de definicion: inicio de linea con sangria, marcador (letra/numero/romano) + ) o . o .-
# + Termino + ':'. Amplio: agarra 'a)', '1)', '1.', '1.-', 'i)', con 1+ espacios de sangria.
ITEM = re.compile(r'(?m)^\s{1,}([a-z]{1,2}|\d{1,2})[.)](?:-)?\s+([^:\n]{2,80}?):\s')
# gatillo de articulo-definiciones (encabezado tipico)
# 2026-08-10: ampliado. El original solo cubria glosarios clasicos ("se entendera por:"), y
# perdia articulos que ENUMERAN definiciones sin esa formula. Caso medido: 1058072/4º dice
# "los recursos que siguen:" y luego "1) Reposicion: Procedera contra..." -> definicion real
# que def_exact no podia inyectar.
# Riesgo medido antes de ampliar: +9 articulos / +31 fragmentos sobre 631 (crecimiento
# controlado, no explota). El gate de >=2 items sigue filtrando articulos normales.
TRIGGER = re.compile(
    r'se entender[aá]|se entiende por|para (los )?efectos'
    r'|que siguen\s*:|los siguientes\s*:|se indican\s*:', re.I)
# lineas de ruido de enmienda intercaladas (Decreto/Ley/Art./D.O.)
# BUG CORREGIDO 2026-08-07: la version anterior era
#   ^\s*(Decreto|Ley|DFL|Art\.|D\.O\.|LEY|DECRETO)\b.*$
# y `Art\.`/`D\.O\.` seguidos de \b NUNCA matcheaban: tras el '.' viene un espacio y entre dos
# caracteres no-palabra no hay frontera. Solo se borraba 'Decreto ...', y las lineas
# 'Art. primero N° 38), i' / 'D.O. 05.06.2024' se colaban DENTRO de las definiciones y ademas
# PARTIAN palabras ('siguiente c' + ruido + 'ociente:'). Afectaba tambien a los 608 fragmentos
# del glosario clasico, no solo a D2.
NOISE = re.compile(r'(?m)^[\s ]*(?:(?:Decreto|Ley|DFL|LEY|DECRETO)\b|Art\.|D\.O\.).*$')

# ---- D2 (2026-08-07): formato LEYENDA DE VARIABLE ----
# Articulos con formula + leyenda de simbolos. NO tienen marcador 'a)' ni TRIGGER de glosario,
# por eso el extractor original los perdia. Dos variantes reales medidas:
#   250604/53  'IFOR\xa0 \xa0 : Indisponibilidad forzada.'          <- token al inicio de linea
#   250604/31  '\xa0 \xa0 DIP: Menor disponibilidad media anual...' <- sangrado con nbsp, tras 'Donde:'
# El token debe PARECER variable (no prosa) o esto matchea 'TÍTULO II:' y cualquier frase.
VARLEG = re.compile(r'(?m)^[\s ]*([A-ZÁÉÍÓÚÑ][A-Za-z0-9áéíóúñÁÉÍÓÚÑ.]{1,11})[\s ]*:[\s ]')
# gatillo: el articulo declara una formula/leyenda
VARLEG_TRIGGER = re.compile(
    r'Donde\s*:|siguiente\s+(expresi[oó]n|cociente|f[oó]rmula)|de acuerdo a la siguiente', re.I)
# encabezados estructurales que SI matchean la forma de token pero NO son variables
VARLEG_STOP = {'TITULO', 'TÍTULO', 'CAPITULO', 'CAPÍTULO', 'PARRAFO', 'PÁRRAFO', 'ANEXO',
               'ARTICULO', 'ARTÍCULO', 'NOTA', 'LEY', 'DECRETO', 'DFL', 'D.O.', 'ENERGIA',
               'ENERGÍA', 'CONSIDERANDO', 'VISTO', 'VISTOS', 'RESUELVO', 'DECRETO.'}


def _is_var_token(tok: str) -> bool:
    """Token con pinta de variable: >=2 mayusculas o siglas con puntos. Filtra prosa
    ('Artículo', 'Nota' tienen 1 sola mayuscula) y encabezados estructurales."""
    if tok.upper().rstrip('.') in VARLEG_STOP:
        return False
    return sum(1 for ch in tok if ch.isupper()) >= 2 or '.' in tok


def extract_varleg(texto):
    """D2: [(simbolo, descripcion)] de un articulo con leyenda de variables, o []."""
    clean = NOISE.sub('', texto)
    # OJO: el gatillo se busca en el texto LIMPIO y SIN saltos, porque las lineas de enmienda
    # PARTEN palabras. Real en 250604/53:
    #   '...a partir del siguiente c\nDecreto 70, ENERGIA\n...\nociente:'
    # es decir 'cociente' queda cortado -> buscarlo en el crudo daba 0 matches y se perdia TON.
    flat = re.sub(r'[\n\r]+', '', clean)
    if not VARLEG_TRIGGER.search(flat):
        return []
    ms = [m for m in VARLEG.finditer(clean) if _is_var_token(m.group(1))]
    if len(ms) < 2:          # mismo gate que el glosario: >=2 items
        return []
    out = []
    for i, m in enumerate(ms):
        sym = m.group(1).strip().rstrip('.')
        start = m.end()
        end = ms[i + 1].start() if i + 1 < len(ms) else len(clean)
        desc = re.sub(r'[\s ]+', ' ', clean[start:end]).strip().strip('.')
        if sym and len(desc) > 15:   # descripcion real, no un resto de formula
            out.append((sym, desc))
    return out


def extract_fragments(texto):
    """Devuelve [(termino, texto_def)] de un articulo-glosario, o [] si no lo es."""
    if not TRIGGER.search(texto):
        return []
    clean = NOISE.sub('', texto)
    matches = list(ITEM.finditer(clean))
    if len(matches) < 2:  # necesita >=2 items para ser glosario (evita partir arts normales)
        return []
    frags = []
    for i, m in enumerate(matches):
        termino = m.group(2).strip()
        start = m.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(clean)
        deftxt = re.sub(r'\s+', ' ', clean[start:end]).strip()
        if termino and len(deftxt) > 5:
            frags.append((termino, deftxt))
    return frags


def main():
    write = os.environ.get("WRITE") == "1"
    with with_connection() as conn, conn.cursor() as cur:
        cur.execute("SELECT id, id_norma, numero, texto FROM articulos WHERE texto IS NOT NULL;")
        arts = cur.fetchall()
    glos = 0; total_frags = 0; frag_records = []
    varleg_arts = 0; varleg_frags = 0
    for aid, id_norma, numero, texto in arts:
        frags = extract_fragments(texto)
        if frags:
            glos += 1; total_frags += len(frags)
            for termino, deftxt in frags:
                frag_records.append({"articulo_id": int(aid), "id_norma": id_norma,
                                     "numero": numero, "termino": termino,
                                     "texto": f"{termino}: {deftxt}"})
        # D2: leyenda de variables (complementario; un articulo puede tener ambos)
        vl = extract_varleg(texto)
        if vl:
            varleg_arts += 1
            have = {t.lower() for t, _ in frags}
            for sym, desc in vl:
                if sym.lower() in have:      # ya capturado por el glosario clasico
                    continue
                varleg_frags += 1
                frag_records.append({"articulo_id": int(aid), "id_norma": id_norma,
                                     "numero": numero, "termino": sym,
                                     "texto": f"{sym}: {desc}"})
    print(f"articulos-glosario detectados: {glos}")
    print(f"fragmentos-definicion totales:  {total_frags}")
    print(f"[D2] articulos con leyenda de variable: {varleg_arts}  -> fragmentos nuevos: {varleg_frags}")

    # cobertura sobre los conceptos que fallan en E0
    try:
        d = json.load(open("data/eval/results/e0_baseline/result.json"))
        fails = [c for c in d["detail"] if c["cat"] == "in_domain" and not c["ok1"]]
        def concept(q): return re.sub(r'^(qu[eé] es|qu[eé] significa|definici[oó]n de|qu[eé] se entiende por)\s+', '', q.strip(), flags=re.I).strip().lower()
        failset = {concept(c["q"]) for c in fails}
        termset = {f["termino"].lower() for f in frag_records}
        covered = {t for t in failset if any(t == ft or t in ft or ft in t for ft in termset)}
        print(f"conceptos que fallan cubiertos por un fragmento: {len(covered)}/{len(failset)}")
        print("  NO cubiertos:", sorted(failset - covered))
    except Exception as ex:
        print("cobertura: skip", ex)

    if not write:
        print("\n[DRY] no se escribio nada. Muestra 5 fragmentos:")
        for f in frag_records[:5]:
            print(f"  [{f['id_norma']}/{f['numero']}] {f['texto'][:90]}")
        json.dump(frag_records, open("data/eval/results/def_fragments_dry.json", "w"), ensure_ascii=False)
        print(f"\n[DRY] guardado data/eval/results/def_fragments_dry.json ({len(frag_records)} frags). WRITE=1 para tabla+embeddings.")
        return

    # ---- WRITE: tabla fragmentos_definicion + embeddings 4b MRL-1024 (misma receta que el corpus) ----
    import json as _json, urllib.request as _u, math as _m
    def embed_1024(text):
        payload = _json.dumps({"model": "qwen3-embedding:4b", "input": [text]}).encode()
        req = _u.Request("http://localhost:11434/api/embed", data=payload, headers={"Content-Type": "application/json"})
        with _u.urlopen(req, timeout=120) as r:
            emb = _json.loads(r.read())["embeddings"][0]
        s = emb[:1024]; nrm = _m.sqrt(sum(x * x for x in s)) or 1.0
        return [x / nrm for x in s]

    print("\n[WRITE] creando tabla fragmentos_definicion + embeddings ...", flush=True)
    with with_connection() as conn, conn.cursor() as cur:
        cur.execute("""CREATE TABLE IF NOT EXISTS fragmentos_definicion (
            id bigserial PRIMARY KEY, articulo_id bigint, id_norma text, numero text,
            termino text, texto text, embedding_4b_1024 vector(1024));""")
        cur.execute("TRUNCATE fragmentos_definicion;")
        conn.commit()
        for i, f in enumerate(frag_records):
            vec = embed_1024(f["texto"])
            cur.execute("INSERT INTO fragmentos_definicion (articulo_id,id_norma,numero,termino,texto,embedding_4b_1024) "
                        "VALUES (%s,%s,%s,%s,%s,%s::vector)",
                        (f["articulo_id"], f["id_norma"], f["numero"], f["termino"], f["texto"], vec))
            if (i + 1) % 50 == 0:
                conn.commit(); print(f"  insertados {i+1}/{len(frag_records)}", flush=True)
        conn.commit()
        cur.execute("CREATE INDEX IF NOT EXISTS idx_fragdef_4b1024 ON fragmentos_definicion "
                    "USING hnsw (embedding_4b_1024 vector_cosine_ops);")
        conn.commit()
    print(f"[WRITE] listo: {len(frag_records)} fragmentos-definicion + indice HNSW.", flush=True)


if __name__ == "__main__":
    main()
