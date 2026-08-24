import json, time, requests
from src.pipelines.prompts import build_answer_prompt, get_answer_system

d = json.load(open('data/eval/results/gen8_paired/result.json'))['detail']
q = next(x for x in d if x['query'] == 'definición de Mora')
prompt = build_answer_prompt(q['query'], q['_docs'])
print('prompt chars:', len(prompt), flush=True)
for npred in (2000, 8000):
    t0 = time.time()
    r = requests.post('http://localhost:11434/api/generate', json={
        'model': 'qwen3:30b-a3b', 'prompt': prompt, 'system': get_answer_system(),
        'stream': False, 'think': True,
        'options': {'num_ctx': 32768, 'num_predict': npred, 'temperature': 0.0}}, timeout=1800)
    j = r.json()
    print(f"num_predict={npred}: t={time.time()-t0:.0f}s eval={j.get('eval_count')} "
          f"done={j.get('done_reason')} thinking={len(j.get('thinking') or '')} "
          f"response={len(j.get('response') or '')}", flush=True)
    print('   resp:', repr((j.get('response') or '')[:200]), flush=True)
