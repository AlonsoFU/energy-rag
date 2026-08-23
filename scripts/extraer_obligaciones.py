"""E4.2 — extraer OBLIGACIONES del articulado del núcleo de mercados.

El LLM local lee cada artículo y devuelve JSON con las obligaciones que contiene.
**Nada entra a la base sin validarse contra el texto**: el sujeto y la evidencia tienen que
aparecer literalmente en el artículo. Un mapa de obligaciones alucinado es peor que no tenerlo
— se vería igual de convincente y llevaría a incumplir un plazo real.

Corpus objetivo: artículos de normas DENTRO del dominio cuyo texto contiene lenguaje de deber.
El filtro de entrada es amplio a propósito (el LLM decide si hay obligación o no); lo que se
aprieta es la SALIDA.

  PYTHONPATH=. venv/bin/python -m scripts.extraer_obligaciones [--limit N] [--dry]
"""
import argparse
import json
import re
import unicodedata

from psycopg.rows import dict_row

from src.components.llm import get_llm_provider
from src.pipelines.generate import _strip_think_block
from src.components.vectorstore import with_connection

MODEL = "ollama/qwen3:30b-a3b"

# Decodificación restringida por esquema (Ollama `format`). Sin esto qwen3 se queda razonando
# y NUNCA emite el JSON: se midió 7962 caracteres de monólogo en inglés y cero salida útil,
# incluso con 3500 tokens de presupuesto y con la directiva `/no_think`.
ESQUEMA = {
    "type": "object",
    "properties": {
        "obligaciones": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "sujeto": {"type": "string"},
                    "accion": {"type": "string"},
                    "destinatario": {"type": ["string", "null"]},
                    "plazo": {"type": ["string", "null"]},
                    "evidencia": {"type": "string"},
                },
                "required": ["sujeto", "accion", "evidencia"],
            },
        }
    },
    "required": ["obligaciones"],
}

PROMPT = """Eres un analista normativo. Lee el artículo y extrae SOLO las obligaciones que
establece de forma explícita.

Una obligación tiene: quién está obligado (sujeto), qué debe hacer (acción), ante quién
(destinatario, si lo dice) y en qué plazo (si lo dice).

REGLAS ESTRICTAS:
- Usa ÚNICAMENTE palabras que aparezcan en el artículo. No interpretes ni completes.
- Si el artículo no impone ninguna obligación, devuelve una lista vacía.
- "evidencia" debe ser una cita LITERAL y continua del artículo (10 a 200 caracteres).
- Si no hay plazo explícito, usa null. NO inventes plazos.

Responde SOLO con JSON, sin texto alrededor:
{{"obligaciones": [{{"sujeto": "...", "accion": "...", "destinatario": null,
                     "plazo": null, "evidencia": "..."}}]}}

ARTÍCULO {art} de {norma}:
{texto}
"""


def _norm(s):
    s = unicodedata.normalize("NFD", (s or "").lower())
    s = "".join(c for c in s if unicodedata.category(c) != "Mn")
    return re.sub(r"\s+", " ", s).strip()


def valida(ob, texto):
    """El sujeto y la evidencia deben estar LITERALMENTE en el artículo."""
    t = _norm(texto)
    suj, ev = _norm(ob.get("sujeto")), _norm(ob.get("evidencia"))
    if not suj or not ev or len(ev) < 10:
        return False, "campos vacios o evidencia muy corta"
    if suj not in t:
        return False, f"sujeto no aparece: {ob.get('sujeto')!r}"
    if ev not in t:
        return False, "evidencia no es cita literal"
    pl = ob.get("plazo")
    if pl and _norm(pl) not in t:
        return False, f"plazo inventado: {pl!r}"
    return True, ""


def objetivo(limit=0):
    with with_connection() as c, c.cursor(row_factory=dict_row) as cur:
        cur.execute("""
            SELECT a.id, a.numero, a.texto, n.tipo, n.numero AS nnum, n.titulo
            FROM articulos a JOIN normas n ON n.id_norma = a.id_norma
            WHERE NOT coalesce((n.metadata->>'fuera_de_dominio')='true', false)
              AND length(a.texto) BETWEEN 200 AND 6000
              AND a.texto ~* '(deber[áa]n?|estar[áa]n? obligad|le corresponder[áa]|
                               tendr[áa]n? que|se obliga|remitir[áa]|informar[áa]|
                               comunicar[áa]|publicar[áa])'
              AND (n.titulo ILIKE '%transferencia%' OR n.titulo ILIKE '%peaje%'
                   OR n.titulo ILIKE '%valoriz%' OR n.titulo ILIKE '%tarif%'
                   OR n.titulo ILIKE '%precio%' OR n.titulo ILIKE '%transmisi%'
                   OR n.numero IN ('20936','62','10'))
            ORDER BY n.tipo, n.numero, a.id
        """)
        r = cur.fetchall()
    return r[:limit] if limit else r


def main(limit=0, dry=False):
    arts = objetivo(limit)
    print(f"artículos candidatos: {len(arts)}", flush=True)
    llm = get_llm_provider()
    n_ob = n_val = n_desc = 0
    motivos = {}

    for i, a in enumerate(arts, 1):
        p = PROMPT.format(art=a["numero"], norma=f"{a['tipo']} {a['nnum']}", texto=a["texto"][:5500])
        try:
            # LLMResponse tiene .text; y qwen3 antepone un bloque <think> que hay que sacar
            # antes de buscar el JSON (si no, el regex agarra llaves del monologo interno).
            # qwen3 razona antes de responder y NO siempre cierra el <think> (bug conocido
            # del proyecto). Por eso: presupuesto amplio de tokens, y se busca el ULTIMO
            # bloque JSON del texto -- el primero suele estar dentro del monologo.
            raw = _strip_think_block(llm.generate(
                p, model=MODEL, temperature=0.0, max_tokens=1800,
                response_format=ESQUEMA).text)
        except Exception as ex:
            print(f"  [{i}/{len(arts)}] LLM fallo: {type(ex).__name__}", flush=True); continue
        obs = None
        for cand in reversed(re.findall(r'\{[^{}]*"obligaciones".*?\]\s*\}', raw, re.S)):
            try:
                obs = json.loads(cand).get("obligaciones", [])
                break
            except Exception:
                continue
        if obs is None:
            continue

        buenas = []
        for ob in obs:
            n_ob += 1
            ok, why = valida(ob, a["texto"])
            if ok:
                buenas.append(ob); n_val += 1
            else:
                n_desc += 1
                motivos[why.split(":")[0]] = motivos.get(why.split(":")[0], 0) + 1

        if buenas:
            print(f"  [{i}/{len(arts)}] {a['tipo']} {a['nnum']} art {a['numero']}: "
                  f"{len(buenas)}/{len(obs)} válidas", flush=True)
            for ob in buenas[:2]:
                print(f"        {ob['sujeto'][:34]} → {ob['accion'][:52]}"
                      f"{' · plazo: ' + ob['plazo'][:26] if ob.get('plazo') else ''}", flush=True)
        if dry or not buenas:
            continue
        with with_connection() as c, c.cursor() as cur:
            for ob in buenas:
                cur.execute("""INSERT INTO obligacion
                    (articulo_id, sujeto, accion, destinatario, plazo, evidencia, validada)
                    VALUES (%s,%s,%s,%s,%s,%s,true) ON CONFLICT DO NOTHING""",
                    (a["id"], ob["sujeto"][:300], ob["accion"][:600],
                     (ob.get("destinatario") or None), (ob.get("plazo") or None),
                     ob["evidencia"][:600]))
            c.commit()

    print(f"\n=== propuestas {n_ob} · VÁLIDAS {n_val} · descartadas {n_desc} "
          f"{'(DRY)' if dry else 'GUARDADAS'} ===", flush=True)
    for k, v in sorted(motivos.items(), key=lambda x: -x[1]):
        print(f"   descartadas por {k}: {v}", flush=True)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--dry", action="store_true")
    a = ap.parse_args()
    main(a.limit, a.dry)
