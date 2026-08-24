import json, litellm
from src.pipelines.prompts import build_answer_prompt, get_answer_system

d = json.load(open('data/eval/results/gen8_paired/result.json'))['detail']
q = next(x for x in d if x['query'] == 'definición de Mora')
prompt = build_answer_prompt(q['query'], q['_docs'])

for think in (False, True):
    resp = litellm.completion(
        model="ollama/qwen3:30b-a3b",
        messages=[{"role": "system", "content": get_answer_system()},
                  {"role": "user", "content": prompt}],
        temperature=0.0, num_ctx=32768, num_predict=2000, think=think,
        timeout=600, num_retries=0,
    )
    m = resp.choices[0].message
    print(f"think={think}: content_len={len(m.content or '')} "
          f"reasoning={len(getattr(m, 'reasoning_content', None) or '')} "
          f"tokens_out={resp.usage.completion_tokens}", flush=True)
    print("   content:", repr((m.content or '')[:160]), flush=True)
    print("   keys:", [k for k in m.model_dump().keys()], flush=True)
