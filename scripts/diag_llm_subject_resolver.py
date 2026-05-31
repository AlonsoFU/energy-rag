"""Test (solo-lectura) del resolver LLM descripción→sujeto.

Hipótesis Paso 2: un LLM local puede leer una query PARAFRASEADA y elegir cuál
concepto curado es el SUJETO (no el contexto). Si acierta, mapeamos por el
índice curado a (norma, artículo) EXACTO → inyección legal-safe (difuso para
ENTENDER, exacto/curado para CITAR).

No genera respuesta, no modifica nada. Mide cuántas de las 15 indep_complex
resuelve al concepto cuyo artículo-definición == gold. Techo conocido: 8/15
(los otros 7 golds no son artículo-definición de ningún concepto).
"""
import json
import sys
from pathlib import Path

from src.components.llm import get_llm_provider
from src.pipelines.concept_injection import _all_concepts, _concept_index
from src.pipelines.normalize import normalize_for_match

EVAL = Path("data/eval/queries_independent.jsonl")
MODEL = sys.argv[2] if len(sys.argv) > 2 else "ollama/qwen3.5:9b"

SYSTEM = (
    "Eres un clasificador jurídico. Te doy una pregunta sobre normativa eléctrica "
    "chilena y una lista numerada de CONCEPTOS definidos. Devuelve SOLO el número "
    "del concepto que es el SUJETO PRINCIPAL de la pregunta (lo que se pregunta), "
    "NO el que aparece como mero contexto o escenario. Si ninguno es el sujeto, "
    "devuelve 0. Responde únicamente con el número, sin texto adicional."
)


def build_prompt(query: str, names: list[str]) -> str:
    lines = "\n".join(f"{i+1}. {n}" for i, n in enumerate(names))
    return (
        f"PREGUNTA: {query}\n\n"
        f"CONCEPTOS:\n{lines}\n\n"
        f"Número del concepto SUJETO (0 si ninguno):"
    )


def main():
    cats = {sys.argv[1]} if len(sys.argv) > 1 else {"indep_complex"}
    rows = [json.loads(l) for l in EVAL.read_text().splitlines() if l.strip()]
    rows = [r for r in rows if r["category"] in cats]

    concepts = _all_concepts()
    names = [c["nombre"] for c in concepts]
    idx = _concept_index()
    llm = get_llm_provider()

    hit = 0
    print(f"== resolver LLM ({MODEL}) sobre {len(rows)} queries ==\n")
    for r in rows:
        q = r["query"]
        gold = (str(r["expected_norma"]), str(r["expected_articulo"]))
        prompt = build_prompt(q, names)
        resp = llm.generate(prompt, model=MODEL, system=SYSTEM,
                            temperature=0.0, max_tokens=10)
        raw = (resp.text or "").strip()
        num = "".join(ch for ch in raw if ch.isdigit())
        picked_n = picked_a = picked_name = None
        if num and num != "0":
            i = int(num) - 1
            if 0 <= i < len(names):
                picked_name = names[i]
                entry = idx.get(normalize_for_match(picked_name))
                if entry:
                    picked_n, picked_a = str(entry[0]), str(entry[1])
        ok = (picked_n, picked_a) == gold
        hit += ok
        tag = "OK  " if ok else "MISS"
        print(f"[{tag}] gold={gold[0]}/{gold[1]}  pick='{picked_name}'→{picked_n}/{picked_a}  (raw='{raw}')")
        print(f"       {q}\n")

    print(f"== RESUMEN ==")
    print(f"resolver acierta (concepto→artículo == gold): {hit}/{len(rows)}  (techo 8/15)")


if __name__ == "__main__":
    main()
