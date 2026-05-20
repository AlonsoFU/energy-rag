"""Post-hoc domain-filtered analysis of the definitive eval (2 runs).

The eval set queries_electrico.jsonl is ~32% contaminated with road/traffic
law (norma 1207690 = Decreto 262 telepeaje vial; 1007469 = DFL 1 Ley de
Tránsito). This script classifies each query by its expected_norma against the
DB, then recomputes grounding on the TRUE electric subset, averaging the 2
runs. It also quantifies the deterministic Ollama hang by domain.
"""
import json
import sys

RUN1 = "data/eval/results/20260519T172842Z.json"
RUN2 = "data/eval/results/20260519T183506Z.json"

# Off-domain normas, classified via DB (titulo) — exhaustive audit:
#   1207690 = DECRETO 262 sitio electrónico de tarifas y peajes (telepeaje vial)
#   1007469 = DFL 1 LEY DE TRÁNSITO
#   1199483 = LEY 21647 reajuste remuneraciones sector público / aguinaldos
OFFDOMAIN = {"1207690", "1007469", "1199483"}
HANG_MS = 300_000  # >= 5 min = the deterministic Ollama hang


def load(path):
    return json.load(open(path))["per_query"]


def classify(row):
    en = str(row.get("expected_norma") or "").strip()
    if en in ("", "None"):
        return "negative"
    if en in OFFDOMAIN:
        return "offdomain"
    return "electric"


def grounding(rows):
    """grounding over rows that produced a generation (non-empty answer)."""
    gen = [r for r in rows if (r.get("answer") or "").strip()]
    if not gen:
        return None, 0, 0
    ok = sum(1 for r in gen if r.get("grounding_pass"))
    return ok / len(gen), ok, len(gen)


def hang_rate(rows):
    if not rows:
        return None, 0, 0
    h = sum(1 for r in rows if (r.get("latency_ms") or 0) >= HANG_MS)
    return h / len(rows), h, len(rows)


def analyze(tag, rows):
    buckets = {"electric": [], "offdomain": [], "negative": []}
    for r in rows:
        buckets[classify(r)].append(r)

    print(f"\n===== {tag} (n={len(rows)}) =====")
    for name in ("electric", "offdomain", "negative"):
        b = buckets[name]
        g, gok, gn = grounding(b)
        hr, hh, hn = hang_rate(b)
        gtxt = f"{g*100:.1f}% ({gok}/{gn})" if g is not None else "n/a"
        htxt = f"{hr*100:.0f}% ({hh}/{hn})" if hr is not None else "n/a"
        print(f"  {name:10s} n={len(b):2d}  grounding={gtxt:16s}  hang>=5min={htxt}")
    # negative_correct: a negative is correct if it refused (empty/refusal answer)
    negs = buckets["negative"]
    if negs:
        refusal = "no encuentro esa información"  # src.pipelines.off_topic.REFUSAL_TEXT
        nc = sum(1 for r in negs
                 if not (r.get("answer") or "").strip()
                 or refusal in (r.get("answer") or "").lower())
        print(f"  negative_correct = {nc}/{len(negs)}")
    return buckets


def main():
    r1, r2 = load(RUN1), load(RUN2)
    b1 = analyze("RUN 1 (172842Z)", r1)
    b2 = analyze("RUN 2 (183506Z)", r2)

    print("\n===== HONEST decomposition (electric positives, hang = FAILURE) =====")
    print("  grounding_pass is a guardrail (cited from pool), NOT answer quality.")
    ar_vals, ga_vals, gt_vals = [], [], []
    for tag, b in (("run1", b1), ("run2", b2)):
        el = b["electric"]
        n = len(el)
        answered = [r for r in el if (r.get("answer") or "").strip()]
        a_rate = len(answered) / n
        g_given_a = (sum(1 for r in answered if r.get("grounding_pass"))
                     / len(answered)) if answered else 0.0
        g_over_total = sum(1 for r in el if r.get("grounding_pass")) / n
        ar_vals.append(a_rate); ga_vals.append(g_given_a); gt_vals.append(g_over_total)
        print(f"  {tag} (n={n}): answered={a_rate*100:.1f}%  "
              f"grounded|answered={g_given_a*100:.1f}%  "
              f"grounded/total={g_over_total*100:.1f}%")
    print(f"\n  >>> AVG answered_rate        = {sum(ar_vals)/2*100:.1f}%  "
          f"(cuelgue/empty = no entrega)")
    print(f"  >>> AVG grounded | answered  = {sum(ga_vals)/2*100:.1f}%  "
          f"(≈tautológico bajo constrained decoding)")
    print(f"  >>> AVG grounded / total     = {sum(gt_vals)/2*100:.1f}%  "
          f"(número honesto: cuelgue cuenta como fallo)")
    print(f"  >>> handoff 'baseline 67.7%' = NO comparable "
          f"(set 35% contaminado + denominador excluía cuelgues)")

    # recall norma-only on electric subset (retrieval is LLM-independent → stable)
    for tag, b in (("run1", b1), ("run2", b2)):
        el = b["electric"]
        rec = sum(1 for r in el if r.get("retrieval_norma_only_hit")) / len(el)
        print(f"  {tag}: electric recall@5 norma-only = {rec*100:.1f}% (n={len(el)})")


if __name__ == "__main__":
    sys.exit(main())
