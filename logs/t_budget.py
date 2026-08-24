import json, requests, time
from src.pipelines.prompts import build_answer_prompt, get_answer_system

d = json.load(open('data/eval/results/gen8_paired/result.json'))['detail']
b = [x for x in d if x.get('on_stats')]
empties = [x for x in b if not (x['on_stats']['text'] or '').strip()][:3]
print(f"probando {len(empties)} queries que dieron respuesta VACIA con think=True/num_predict=2000\n", flush=True)
for q in empties:
    prompt = build_answer_prompt(q['query'], q['_docs'])
    print(f"### {q['query'][:50]}", flush=True)
    for npred in (2000, 6000):
        t0 = time.time()
        r = requests.post('http://localhost:11434/api/generate', json={
            'model': 'qwen3:30b-a3b', 'prompt': prompt, 'system': get_answer_system(),
            'stream': False, 'think': True,
            'options': {'num_ctx': 32768, 'num_predict': npred, 'temperature': 0.0}}, timeout=1800)
        j = r.json()
        th = len(j.get('thinking') or ''); rs = len(j.get('response') or '')
        print(f"   npred={npred:5} t={time.time()-t0:5.0f}s eval={j.get('eval_count'):5} "
              f"done={j.get('done_reason'):8} thinking={th:6} response={rs:5}", flush=True)
