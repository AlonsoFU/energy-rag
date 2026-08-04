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
TRIGGER = re.compile(r'se entender[aá]|se entiende por|para (los )?efectos', re.I)
# lineas de ruido de enmienda intercaladas (Decreto/Ley/Art./D.O.)
NOISE = re.compile(r'(?m)^\s*(Decreto|Ley|DFL|Art\.|D\.O\.|LEY|DECRETO)\b.*$')


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
    for aid, id_norma, numero, texto in arts:
        frags = extract_fragments(texto)
        if not frags:
            continue
        glos += 1; total_frags += len(frags)
        for termino, deftxt in frags:
            frag_records.append({"articulo_id": int(aid), "id_norma": id_norma,
                                 "numero": numero, "termino": termino,
                                 "texto": f"{termino}: {deftxt}"})
    print(f"articulos-glosario detectados: {glos}")
    print(f"fragmentos-definicion totales:  {total_frags}")

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
