# 04 · Evaluación

## Sets de preguntas
| set | archivo | n | quién lo escribió | para qué |
|---|---|---|---|---|
| dev (operativas) | `data/eval/queries_operativas_v1.jsonl` | 114 | el asistente | set principal; incluye 50 coloquiales |
| held-out (fraseos) | `data/eval/queries_fraseos_v1.jsonl` | 64 | el asistente | caza sobreajuste; fraseo formal |
| **reales con gold de terceros** | `data/eval/queries_publicas_gold_v1.jsonl` | **16** | SEC, CGE, Coordinador | el artículo correcto lo dice la fuente, verificado en la DB |
| reales sin gold | `data/eval/preguntas_publicas_v1.jsonl` | 80 | SEC (41), Ministerio (8), CGE (8), BCN (6), Coordinador (10), SERNAC (3), Enel (3), ODECU (1) | textuales, con URL; base para etiquetar más |
| fallas de generación | `data/eval/queries_techo_gen_v1.jsonl` | 13 | derivado | exp #87 |

**No tocar:** `data/eval/queries_diverse.jsonl`, `data/eval/_rem.jsonl`, `data/eval/ft_pairs.jsonl`.

Sesgos conocidos: dev y held-out los escribió el asistente; 4 gold de dev apuntan al decreto
derogado de 1935 (error del eval); el set real tiene n=16 (IC ~ ±22 puntos). El usuario no
aportará preguntas propias; las 80 públicas son la fuente independiente.

## Métricas (`scripts/eval_metrics.py`)
| métrica | significa |
|---|---|
| `cita_ok` | alguna cita apunta al artículo correcto (o a un `also_gold`) |
| `cita_limpia` | `cita_ok` y además precisión ≥ umbral (no rocía citas) |
| `precision` | fracción de citas que son gold |
| `refuso` / `rechazo_ok` | respondió «no encontré» / y correspondía |
| fidelidad (juez #68) | ¿la frase dice lo que dice el artículo? `scripts/experimentos/exp_fidelidad.py` |

## Cómo se mide un cambio
```bash
# una corrida con la config adoptada (+ flags/parámetros a probar)
env PYTHONPATH=. SOLO_ON=1 FLAGS=flag_a,flag_b SETCFG=param=valor \
    SET=data/eval/queries_operativas_v1.jsonl NAME=mi_corrida \
    venv/bin/python -m scripts.exp_think_paired
# comparación pareada (McNemar) contra una base
env PYTHONPATH=. venv/bin/python scripts/comparar_corridas.py \
    data/eval/results/BASE data/eval/results/mi_corrida
```
- `FLAGS` prende booleanos; `SETCFG` fija parámetros (se aplica dentro de cada pregunta, después de la config).
- `VAR` elige qué se alterna entre brazos (default `answer_think`); con `SOLO_ON=1` corre un solo brazo.
- `MODEL=ollama/...` cambia el modelo de redacción.
- Resultados en `data/eval/results/NAME/result.json`, con `db_huella`.

Diagnóstico «¿búsqueda o redacción?»: `scripts/diag_donde_falla.py` cruza el pool recuperado
con lo que respondió el modelo (estado final: 31 fallas de dev = 18 RETRIEVAL + 13 GENERACION).
Tiempos por etapa: `scripts/medir_tiempos_busqueda.py`.

## Red golden: probar un refactor sin re-medir
El pipeline es determinista, así que un refactor se **prueba**: si la salida cambia, está mal.
```bash
PYTHONPATH=. venv/bin/python -m scripts.red_golden                          # graba la base (~15 min)
PYTHONPATH=. venv/bin/python -m scripts.red_golden --salida /tmp/nueva.json
PYTHONPATH=. venv/bin/python -m scripts.red_golden --comparar data/eval/redes/busqueda_base.json /tmp/nueva.json
```
- **Red de búsqueda** (`scripts/red_golden.py`, ~15 min): los 10 artículos de cada una de las
  194 queries, en orden, con `db_huella`. Para cualquier cambio en `retrieve.py` o
  `vectorstore.py`. Base vigente: `data/eval/redes/busqueda_base.json`. `--comparar` sale con
  código 1 si un solo puesto cambió, o si la huella del corpus difiere.
- **Red completa** (~4 h): `scripts.exp_think_paired` sobre dev + held-out. Para `generate.py`.
- `--autoprueba` verifica que el comparador ve un cambio de orden y un corpus distinto.

## Reglas (aprendidas a golpes)
1. **Criterio escrito ANTES de correr**, en `scripts/plan_maestro.txt`, con predicción registrada.
2. **dev Y held-out**; si discrepan, no se adopta. Si se puede, también las 16 reales.
3. **Misma huella de corpus** en base y brazo. Si el monitor aplicó cambios entre medio, la base caducó.
4. **Pipeline determinista**: `selfcons_temperature=0.0`. Con 0.7 cambiaba el 11 % de los textos entre corridas idénticas.
5. **Leer a mano las fallas** antes de otro experimento: el defecto de notas marginales (#84) salió de leer 28 fallas, no de un experimento.
6. Un `result.json` de más de 48 h con el mismo `NAME` ya no se reanuda (el harness aborta): una vez «corrió» en 7 s sobre datos de otro corpus.
7. Las bases hasta 2026-09-20 (`combo0_*`, `l69_*`, `fix84_*`) se midieron con `self_consistency_n=3`; el harness ahora usa la config (n=1). Para comparar contra ellas: `SETCFG=self_consistency_n=3`.

## Bases vigentes
`l69_dev`, `l69_holdout`, `pub_final` (corpus final, n=3). Caducan con el próximo monitor que
aplique cambios.
