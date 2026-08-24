import json
from src.core import config as cfg
from src.components.llm import get_llm_provider
from src.pipelines.generate import generate_answer

d = json.load(open('data/eval/results/gen8_paired/result.json'))['detail']
q = next(x for x in d if x['query'] == 'definición de Mora')
llm = get_llm_provider()
for think in (False, True):
    cfg.settings.ollama_think = think
    res = generate_answer(q['query'], q['_docs'], llm=llm, model="ollama/qwen3:30b-a3b")
    t = res['text']
    print(f"ollama_think={think}: len={len(t)}  grounded={res.get('grounding_pass')}", flush=True)
    print("   ", repr(t[:200]), flush=True)
