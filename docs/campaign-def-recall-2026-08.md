# Campaña: recall de definiciones (2026-08)

Objetivo: subir cita_ok atacando el frente de definiciones ("qué es X"). Todo medido con
disciplina (flag-gated, dev+holdout, McNemar pareado). **Ningún experimento se adoptó** — pero
el diagnóstico quedó cerrado y quedan 2 palancas reales identificadas.

## Método nuevo: E0 baseline ROBUSTO + McNemar
Los sets chicos (coloquial 39 / dev 44 / holdout 18) MIENTEN para deltas chicos (ruido ±2=1σ,
LLM flickea ±1). Se adoptó como set primario **`balanced_v2` (339q: 279 in_domain + 30 off_domain
+ 30 off_corpus-rechazo)** + **McNemar pareado** (≥5-6 flips netos para p<0.05).

**Baseline E0 (config campeona 4B-1024+alias+30b-a3b, `scripts/exp_e0_baseline.py`):**
- in_domain **173/279 (62%)** · off_domain 21/30 · rechazo **30/30 (100%)**.
- Los sets chicos daban 82-95% → eran optimistas. 62% es el número real y robusto.

## Diagnóstico (instantáneo, sin gen)
De las 106 fallas in_domain:
- **89 = RECALL** (gold ni en top-10) · 17 = GEN (gold en top-10, no citó).
- Causa raíz: los golds son **artículos-glosario de ~10k chars en 1 solo chunk** (ej 250604/13,
  1160108/2). BGE le da **0.00** al chunk gigante (dilución de ~30 defs) → el gold no entra.

## Experimentos (todos medidos, NINGUNO adoptado)
| exp | qué | resultado | veredicto |
|-----|-----|-----------|-----------|
| **M1** pool 50→100 | más candidatos al reranker | +3, p=0.25 | RUIDO. El gold no está en rank 50-100 tampoco |
| **G1** grafo concepto→art | cablear aristas define_termino | **muerto** | 0/45 fallas tienen aristas art-level correctas (48/371 conceptos las tienen; 0 matchean gold) |
| **M2** def_fragments (inyección) | 1def=1frag AL LADO del gigante, RRF | −10 | NEGATIVO, pero **contaminado por ruido de gen** (método comparaba gen nueva vs vieja) |
| **rechunk** (limpio) | REEMPLAZA gigante por def-fragments, McNemar pareado | **+7/−10, p=0.63** | **FLAT**. El −10 de M2 era casi todo ruido de gen; efecto real ~plano |

## Infra construida (flag-gated, default OFF)
- `scripts/build_def_fragments.py`: detecta artículos-glosario y extrae 1 def = 1 fragmento.
  Detector: gatillo ("se entenderá por / para los efectos") + ≥2 ítems `a)`/`1)`/`1.`/`i)`
  (sangría flexible). **62 artículos → 608 definiciones**, cobertura 33/45 de las fallas.
- Tabla `fragmentos_definicion` (608 filas, embedding_4b_1024 + HNSW), mapea al artículo padre.
- `vectorstore.search_vector_def_4b_1024` (parent-doc) + `exclude_glossary` param.
- `retrieve._is_definition_query` (gate por intención) + branch def_fragments RRF.
- Flags: `def_fragments`, `glossary_exclude` (ambos default OFF).

## Los 2 MUROS reales (para las siguientes palancas)
1. **El reranker prefiere el artículo FUNCIONAL sobre la DEFINICIÓN.** Ej "qué es Coordinador":
   def-fragment 250604/13 = 0.981 pero art 258171/212-1 (funciones) = 0.9985 → gana el funcional,
   la def no entra al top-10. El mecanismo (def-fragment) SÍ sube el gold de 0.00→0.98, pero el
   reranker lo deja 2º. → palanca **RK1: reranker Qwen3-Reranker-4B/8B** (gap ~14pts en benchmark).
2. **Golds ROTOS en balanced_v2** (auto-generados). Ej: `mora→250604/5°`=reliquidaciones (no def);
   `vehículo→1155887/7°`=enmienda (no def); `Superintendencia→29819/2 D`=granularidad de letra.
   Parte del 62% es **ruido de eval**. → **E0b: auditar/arreglar golds + also_gold** (barato, sin gen).

## Aprendizajes de método
- **Medición pareada obligatoria:** comparar gen-nueva vs gen-vieja mete el flicker del LLM como
  flips falsos (M2 "−10" era ruido). Re-generar AMBOS brazos en la misma sesión lo cancela.
- **El screen sigue mintiendo:** el def-fragment scoreaba 0.98 (parecía win) pero e2e = flat.
- **Desconexión del PC wedgea los runs** (socket httpx muerto que no erroriza) → scripts deben ser
  RESUMIBLES (guardar por-query, saltar los ya hechos). `exp_rechunk_clean.py` lo implementa.
- Correr 1 solo proceso (procesos duplicados se pelean ollama → lentísimo + result.json corrupto).

## E0b — auditar/limpiar golds (HECHO, `scripts/audit_golds.py`)
- `queries_balanced_v2_clean.jsonl`: **126 also_gold** agregados (conceptos definidos en varias
  normas ahora aceptan la def alternativa válida). Fuente: `fragmentos_definicion` (donde se define X).
- **EL WIN de la campaña.** Reveló que el recall real es **85%**, no 62%:
  - **BGE gold@10 sobre eval limpio = 237/279 (85%)** (screen RK1).
  - El "62%" de E0 era **injusticia de eval** (rechazaba defs alternativas válidas) + gen.

## RK1 — reranker Qwen3-Reranker-4B (MUERTO, screen `scripts/exp_rk1_screen.py`)
- gold@10: BGE **237/279** vs Qwen3 **239/279** → **Δ=+2 (ruido)**. Y Qwen3 **17× más lento**
  (1591s vs 93s). El reranker NO es el muro — ambos meten ~85% de golds al top-10.
- Los ~40 que faltan es que el gold **ni entra al pool** (retrieval), no reranking. NO adoptar.
- Clase `Qwen3Reranker` queda en reranker.py (RERANKER_KIND=qwen3), OOM-safe (logits_to_keep=1).

## Estado real (post-campaña)
- **Frente retrieval/reranker AGOTADO:** M1/G1/M2/rechunk/RK1 todos negativos. Retrieval ya da 85% gold@10.
- **El gap real ahora es GEN:** gold en top-10 (85%) pero el LLM no siempre lo cita. Ahí está el margen.

## RESULTADO FINAL — re-baseline sobre eval LIMPIO (`data/eval/results/e0_clean`)
| categoría | LIMPIO (also_gold) | sucio (E0) | Δ |
|-----------|--------------------|-----------|---|
| in_domain | **226/279 (81%)** | 62% | **+19** |
| rechazo (off_corpus) | 30/30 (100%) | 100% | = |
| off_domain | 21/30 (70%) | 70% | = |

**El +19 vino 100% de arreglar el eval (also_gold), CERO modelos.** El "62%" era injusticia de métrica.
cita_ok limpio (81%) ≈ gold@10 (85%) → **casi no hay gap de GEN**: si el gold está en top-10, el LLM lo cita.

## Audit de las 53 fallas restantes (in_domain limpio)
- **11 GEN** (gold en top-10, no citó) — chico, ruido/prompt.
- **42 RECALL** (gold ni en top-10), mezcla de:
  - **golds AÚN rotos** (Mora `250604/5`=no existe, es 5°; Reposición `29819/2 D`=granularidad letra)
    → el audit E0b fue laxo (palabra-en-art), quedan por limpiar → el techo real es >81%.
  - **glosario-enterrado** (Estado Deteriorado, Cliente, Ajustes) → def_fragments los rescata pero
    era net-flat (rescata unos, desplaza otros).

## Golds AÚN rotos (audit v2, escaneo amplio de artículos-Definiciones)
De las 29 concepts-falla in_domain: **10 tienen la def REAL ya en el top-10, solo el gold estaba
errado** (Mora→realmente 1207690/3 no 250604/5; Reposición, Proyecto, Bases de Licitación, Costo
de Falla ×2, Sistema Eléctrico Nacional, DIP, Informe Definitivo, Tránsito). Son **15 queries**.
- **Baseline corregido: 226+15 = 241/279 = ~86%** (estimado; el sistema YA recupera bien, el gold
  mentía). Las otras 14 = retrieval real (glosario-enterrado); 5 = acrónimos/formato raro.
- `audit_golds.py` v2 agrega escaneo amplio (`Concepto:` / `se entiende por Concepto`) → **159
  also_gold** (antes 126). Eval `queries_balanced_v2_clean.jsonl` regenerado.
- Nota: ~86% es límite superior estimado (cita_ok≈gold@10); confirmar exacto = re-generar sobre v2.

## CONCLUSIÓN de la campaña
- **El sistema real está en ~81% (probablemente ~85%+ con eval 100% limpio), NO roto en 62%.**
- **Frente retrieval/reranker AGOTADO** (M1/G1/M2/rechunk/RK1 todos negativos) — no había mucho que ganar.
- **La mejor "mejora" de toda la campaña fue arreglar la métrica** (E0b also_gold, +19).
- Retorno decreciente. El 19% restante ≈ mitad eval-roto (limpiable), mitad retrieval-duro (glosario).

## Siguiente (bajo retorno, opcional)
1. Terminar de limpiar golds rotos (Mora, Reposición, letra-format) → techo real >81%.
2. Los 11 GEN-fails: self-consistency / prompt (margen chico).
3. Glosario-enterrado: def_fragments ayuda pero net-flat → no adoptar sin gating más fino.
