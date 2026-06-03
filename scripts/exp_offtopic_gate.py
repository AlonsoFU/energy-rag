"""EXP: comparar palancas para el guard de off-topic (¿cuál generaliza?).

Mide, por query, señales candidatas de "pertenece al dominio":
  S0  oov_ratio          — guard actual (léxico, bolsa de palabras)
  S3  oov_ratio_syn      — S0 + diccionario coloquial→legal curado (anticipado)
  S1  bge_max            — máx score cross-encoder BGE sobre el pool (semántico, lo que ya computa)
  S2  vec_max            — máx coseno embedding sobre el pool (semántico)
Para positivos (coloquial in-domain) además: gold_rank post-BGE (¿es recuperable si pasa el gate?).

Benchmark: POS = coloquial in-domain (deben PASAR); NEG = off-topic. NEG dividido en
  N1 claro (pisco/mundial/auto) y N2 eléctrico-pero-no-en-normas (tarifa Atacama, Ralco MW).
Conclusión: para cada señal, umbral que mejor separa POS de NEG y el costo (cuántos N2 se cuelan).

Uso: ./venv-gpu/bin/python -m scripts.exp_offtopic_gate
"""
import json
from src.components.embedder import Qwen3Embedder
from src.components.reranker import get_reranker
from src.components.vectorstore import PostgresStore
from src.pipelines.retrieve import rrf_fusion, _length_weights
from src.pipelines.off_topic import is_off_topic, _corpus_vocab, _TOKEN_RE, _STOPWORDS

# POS: coloquial in-domain (de queries_complex_v3), con gold
POS = [(json.loads(l)["query"], f"{json.loads(l)['expected_norma']}/{json.loads(l)['expected_articulo']}")
       for l in open("data/eval/queries_complex_v3.jsonl") if json.loads(l)["category"] == "cx_coloquial"]

# NEG1: off-topic CLARO
NEG1 = [
    "receta de pan amasado", "quién ganó el mundial 2022", "cuántos planetas tiene el sistema solar",
    "cómo se cambia una rueda pinchada del auto", "receta de pisco sour",
]
# NEG2: eléctrico-TEMÁTICO pero NO respondible desde las normas (factual)
NEG2 = [
    "cuál es la tarifa del kilowatt-hora residencial en Atacama este mes",
    "qué empresa ganó la última licitación de suministro eléctrico",
    "cuántos megawatts de potencia instalada tiene la central Ralco",
    "cómo conecto un panel solar en el techo de mi casa paso a paso",
]

# Diccionario coloquial→legal (curación ANTICIPADA, para medir cuán lejos llega)
SYN = {
    "máquina": "dispositivo", "respirar": "electrodependiente", "enchufado": "electrodependiente",
    "cajón": "empalme", "aparatito": "medidor", "cuenta": "suministro", "boleta": "suministro",
    "luz": "electricidad", "sobra": "excedentes", "fábrica": "potencia", "vuelto": "remuneración",
    "cortar": "suspensión", "papá": "usuario", "pared": "empalme",
}


def oov_ratio(q, extra_vocab=None):
    vocab = _corpus_vocab() if extra_vocab is None else (_corpus_vocab() | extra_vocab)
    toks = {m.group(0).lower() for m in _TOKEN_RE.finditer(q)} - _STOPWORDS
    if not toks:
        return 0.0
    return len(toks - vocab) / len(toks)


def syn_oov(q):
    # añade los términos legales mapeados de las palabras coloquiales presentes
    toks = {m.group(0).lower() for m in _TOKEN_RE.finditer(q)}
    mapped = {SYN[t] for t in toks if t in SYN}
    extra = {m.group(0).lower() for s in mapped for m in _TOKEN_RE.finditer(s)}
    # quitamos del OOV las palabras coloquiales que tienen mapeo (se consideran in-domain)
    toks2 = ({m.group(0).lower() for m in _TOKEN_RE.finditer(q)} - _STOPWORDS) - set(SYN)
    vocab = _corpus_vocab() | extra
    if not toks2:
        return 0.0
    return len(toks2 - vocab) / len(toks2)


def signals(store, emb, rr, q, gold=None):
    bm25 = store.search_bm25(q, top_k=50)
    vec = store.search_vector(emb.embed([q])[0], top_k=50)
    vec_max = max((c.get("score", 0.0) for c in vec), default=0.0)
    fused = rrf_fusion([bm25, vec], k=60, weights=_length_weights(q))[:50]
    bge_max, gold_rank = 0.0, None
    if fused:
        scored = rr.rerank(q, [c["contextual_text"] for c in fused], top_k=30)
        bge_max = max((s for _, s in scored), default=0.0)
        if gold:
            order = [fused[i] for i, _ in scored]
            gn, ga = gold.split("/", 1)
            for i, c in enumerate(order):
                if str(c.get("id_norma")) == gn and str(c.get("articulo_numero")) == ga:
                    gold_rank = i + 1; break
    return dict(oov=oov_ratio(q), oov_syn=syn_oov(q), vec_max=vec_max, bge_max=bge_max, gold_rank=gold_rank)


def main():
    store, emb, rr = PostgresStore(), Qwen3Embedder(), get_reranker()
    print(f"reranker={type(rr).__name__}\n")
    rows = []
    for q, g in POS:
        s = signals(store, emb, rr, q, g); s["grp"] = "POS"; s["q"] = q; rows.append(s)
    for q in NEG1:
        s = signals(store, emb, rr, q); s["grp"] = "NEG1"; s["q"] = q; rows.append(s)
    for q in NEG2:
        s = signals(store, emb, rr, q); s["grp"] = "NEG2"; s["q"] = q; rows.append(s)

    for grp in ("POS", "NEG1", "NEG2"):
        print(f"=== {grp} ===")
        for r in rows:
            if r["grp"] != grp:
                continue
            gr = f" gold_rank={r['gold_rank']}" if grp == "POS" else ""
            print(f"  oov={r['oov']:.2f} oovSyn={r['oov_syn']:.2f} vec={r['vec_max']:.3f} bge={r['bge_max']:.3f}{gr}  {r['q'][:48]}")

    # separación: para cada señal, mejor umbral (POS pasa, NEG rechaza)
    print("\n=== SEPARACIÓN (POS deben PASAR, NEG rechazar) ===")
    def evaluate(key, hi_is_indomain):
        # umbral: barremos; in-domain si signal>thr (hi_is_indomain) o signal<thr (oov)
        best = None
        vals = sorted(set(r[key] for r in rows))
        for thr in vals + [vals[-1] + 1e-6]:
            if hi_is_indomain:
                pos_pass = sum(1 for r in rows if r["grp"] == "POS" and r[key] >= thr)
                neg_ref = sum(1 for r in rows if r["grp"] != "POS" and r[key] < thr)
            else:
                pos_pass = sum(1 for r in rows if r["grp"] == "POS" and r[key] <= thr)
                neg_ref = sum(1 for r in rows if r["grp"] != "POS" and r[key] > thr)
            score = pos_pass + neg_ref
            if best is None or score > best[0]:
                n1 = sum(1 for r in rows if r["grp"]=="NEG1" and ((r[key]<thr) if hi_is_indomain else (r[key]>thr)))
                n2 = sum(1 for r in rows if r["grp"]=="NEG2" and ((r[key]<thr) if hi_is_indomain else (r[key]>thr)))
                best = (score, thr, pos_pass, n1, n2)
        nP = sum(1 for r in rows if r["grp"]=="POS")
        _, thr, pp, n1, n2 = best
        print(f"  {key:8s} thr={thr:.3f}: POS pasan {pp}/{nP} | NEG1 rechaza {n1}/{len(NEG1)} | NEG2 rechaza {n2}/{len(NEG2)}")
    evaluate("oov", False)
    evaluate("oov_syn", False)
    evaluate("vec_max", True)
    evaluate("bge_max", True)
    gr = [r["gold_rank"] for r in rows if r["grp"] == "POS"]
    print(f"\nPOS gold recuperable (rank≤10) si pasa el gate: {sum(1 for x in gr if x and x<=10)}/{len(gr)}")


if __name__ == "__main__":
    main()
