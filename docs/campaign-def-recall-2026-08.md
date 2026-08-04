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

## Siguiente (orden)
1. **E0b** — auditar golds de balanced_v2 (rotos + granularidad de letra + multi-norma→also_gold).
   Barato, no sufre desconexiones, limpia la métrica para todo lo demás.
2. **RK1** — upgrade reranker bge→Qwen3-Reranker, medido sobre el eval ya limpio. Ataca el muro 1.
