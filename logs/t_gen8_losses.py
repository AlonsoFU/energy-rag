"""De las 17 perdidas de GEN8: la cita del brazo ON apunta a un articulo que DEFINE
el termino (definicion alternativa valida -> injusticia de eval) o a uno que no (error real)?"""
import json, re, unicodedata
from src.storage.connection import with_connection
from src.pipelines.grounding import extract_citations, _normalize_art
from src.pipelines.retrieve import _definition_concept

def strip(s):
    return "".join(c for c in unicodedata.normalize("NFD", s or "") if unicodedata.category(c) != "Mn").lower()

def pats(c):
    c = re.escape(strip(c))
    return [r'(^|[^a-z0-9])' + c + r'\.?\s*:', r'se entiende(?:ra)? por\s+"?' + c,
            r'se entender[aá]\s+por\s+"?' + c, r'se denomina(?:ra)?\s+"?' + c,
            r'definicion de\s+"?' + c]

d = json.load(open('data/eval/results/gen8_paired/result.json'))['detail']
b = [x for x in d if x.get('off_stats') and not x.get('err')]
loss = [x for x in b if x['ok_off'] and not x['ok_on']]

with with_connection() as conn, conn.cursor() as cur:
    cur.execute("SELECT id_norma, numero, texto FROM articulos")
    idx = {(str(n), _normalize_art(str(a))): strip(t) for n, a, t in cur.fetchall()}

vacia = alt = err = 0
for x in loss:
    txt = (x['on_stats']['text'] or '').strip()
    if not txt:
        vacia += 1; print(f"  VACIA        | {x['query'][:46]}"); continue
    c = _definition_concept(x['query']) or x['query']
    cits = [(str(n), _normalize_art(str(a))) for n, a in extract_citations(txt)]
    ok_alt = [ct for ct in dict.fromkeys(cits)
              if ct in idx and any(re.search(p, idx[ct]) for p in pats(c))]
    if ok_alt:
        alt += 1; print(f"  DEF ALTERNATIVA VALIDA -> {ok_alt[0][0]}/{ok_alt[0][1]:8} | {x['query'][:40]}")
    else:
        err += 1; print(f"  ERROR REAL   cits={[f'{a}/{n}' for a,n in list(dict.fromkeys(cits))[:3]]} | {x['query'][:40]}")

print(f"\n  de {len(loss)} perdidas: {vacia} VACIAS (tecnico) | {alt} DEF ALTERNATIVA VALIDA (eval) | {err} ERROR REAL")
