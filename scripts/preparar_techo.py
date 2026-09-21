"""exp #87: arma el set de fallas de GENERACION (el gold llega al pool y el modelo cita otro).

Solo ahi un modelo mejor puede ayudar: en las de RETRIEVAL el modelo nunca ve el articulo.
Lee el diagnostico mas reciente (diag_donde_falla sobre el estado final) y escribe
data/eval/queries_techo_gen_v1.jsonl con esas filas del set dev.
"""
import json
from pathlib import Path
diag = json.loads(Path("data/eval/results/donde_falla_top10_pool50_rr10.json").read_text())
gen = {d["query"] for d in diag if d["clase"] == "GENERACION"}
rows = [l for l in open("data/eval/queries_operativas_v1.jsonl") if l.strip() and json.loads(l)["query"] in gen]
Path("data/eval/queries_techo_gen_v1.jsonl").write_text("".join(rows))
print(f"fallas de generacion: {len(rows)}  (retrieval: {sum(d['clase']=='RETRIEVAL' for d in diag)}, aciertos: {sum(d['clase']=='ACIERTA' for d in diag)})")
assert rows, "0 fallas de generacion: no hay nada que medir"
