# Handoff 2026-06-06 — RESULTADOS del experimento largo coloquial (Fases A/B/C)

> Ejecuta el plan de `handoff-2026-06-05.md`. Veredicto corto: **las 3 fases dieron
> negativo/wash**. El residual coloquial (registro cotidiano↔legal) NO se cerró con
> ninguna palanca probada en este hardware. El sistema base queda intacto, sin cambios
> de producción. Todo lo nuevo es flag-gated default OFF o artefactos de experimento.

---

## Resumen ejecutivo

| Fase | Qué se probó | Resultado | Decisión |
|---|---|---|---|
| **A** | Reformulación selectiva coloquial→legal (PreQRAG), aditiva vector-only, flag-gated | Generación: coloquial cita_ok **26→27** (+1), holdout **17→16** (−1), dev ≈0 | **No adoptar**. Flag `selective_reform` default OFF |
| **B** | Entity/concept anchoring (inyectar artículo de la entidad implícita) | **Inviable**: los golds son artículos sustantivos, no definiciones; el grafo no los conecta (solo `cita` débiles; `202975/76` sin aristas) | **No implementar** |
| **C** | Fine-tune Qwen3-Embedding-0.6B con 1438 pares sintéticos coloquial→artículo | Pure-vector held-out: v1 suave **25→26** (+1, sin regresión); v2 fuerte **25→22** (−3, overfit) | **No adoptar**. Embedder de producción sin cambios |

Criterio de éxito (≥+4 en coloquial sin regresión) **no se cumplió en ninguna fase**.

---

## FASE A — Reformulación selectiva (detalle)

**Implementación (flag-gated, default OFF):**
- `src/pipelines/expansion.py::selective_reform(query, llm)` — un call LLM condicional:
  reescribe a registro legal SOLO si la query es coloquial; si ya es legal → `IGUAL` → `""`.
- `src/core/config.py::selective_reform: bool = False` (env `SELECTIVE_REFORM=1`).
- Cableado **aditivo y vector-only** en `SimpleRetriever._search_text` Y `ComplexRetriever`
  (la query original queda en BM25/rerank). **Hallazgo de cableado:** 32/39 coloquiales
  rutean a *complejo*, no a *simple* → conectar solo Simple no habría servido.

**Medición (Ollama 9b, top_k=10, gate/golds corregidos):**
```
coloquial(target)  cita_ok  26/39 → 27/39  (+1)   grounded 39→39   answered 34→33
holdout(no-reg)    cita_ok  17/18 → 16/18  (−1)
dev(no-reg)        cita_ok  37/44 → ~37/44 (≈0; el run ON timeoutó a 90min)
```
**Por qué no convierte:** el +6 de retrieval del experimento original (`exp_selective_reform.py`)
se midió en el pipeline **simple**. En producción los coloquiales van a **complejo**, donde la
reforma es 1 de 7 señales de query y se solapa con el hyde/multi-query que complejo ya hace →
el aporte marginal se diluye a ruido. Cuello = generación + mismatch simple↔complejo, no retrieval.

## FASE B — Entity anchoring (por qué es inviable para este set)

Sonda (`diag` en sesión): `find_subject_concept` no dispara en NINGUNO de los coloquiales
duros (describen la entidad, no la nombran). Los golds (`258171/118` tope de ganancia,
`258171/212` quién paga el Panel, `202975/76` dónde reclamo) son **artículos sustantivos, no
definiciones de entidad**. Sus aristas en `referencias` son solo `cita` débiles a conceptos
genéricos (Ministerio, CNE); `202975/76` no tiene ninguna arista. Inyectar la definición de
SEC/Panel/CNE (lo que hace `inject_definition`) no toca esos golds. Mecanismo mal apuntado →
no se implementa. (Salvataje posible pero ya explorado y descartado: subir el boost `cita` de
la entidad implícita = territorio `graph_boost_all`, con riesgo de falsos positivos.)

## FASE C — Fine-tune del embedder (detalle)

**Dataset** (`scripts/ft_gen_dataset.py` → `data/eval/ft_pairs.jsonl`): 1438 pares
(coloquial sintético → texto de artículo), 719 artículos de las 5 normas eléctricas. **Held-out
honesto:** los 39 artículos gold reales de `queries_coloquial_v2` se EXCLUYERON del
entrenamiento → cualquier mejora sería generalización de registro, no memorización.

**Entrenamiento** (`scripts/ft_train.py`, MultipleNegativesRankingLoss, GTX 1080 8GB, fp32):
- v1 suave: congela capas 0-19, entrena top-8 + norm, 2 épocas, batch 8.
- v2 fuerte: congela 0-7, entrena 8-27 (315M) + grad checkpointing, 3 épocas, batch 4.

**Eval pure-vector** (`scripts/ft_eval.py`, gold-artículo∈top10, índice = 2921 artículos):
```
                 BASE   v1(suave)   v2(fuerte)
coloquial(tgt)   25/39  26 (+1)     22 (−3)
dev(no-reg)      22/44  22 (0)      20 (−2)
holdout(no-reg)  17/18  17 (0)      15 (−2)
extreme(no-reg)   9/18  10 (+1)      8 (−1)
```
**Lectura:** v1 es ruido (+1, ±1 es ruido a n=39). v2 **overfittea al estilo sintético** y
degrada TODO — el held-out gold-leído-de-la-ley lo detecta. Fine-tune NO cierra el registro.

**Por qué falla el fine-tune (hipótesis):**
1. Dataset chico (1438) + held-out chico (39) → alta varianza, overfit fácil.
2. Las preguntas sintéticas las genera el MISMO LLM que queremos puentear → enseñan su estilo
   de paráfrasis, no el registro coloquial humano real.
3. Qwen3-0.6B base ya es fuerte; un FT parcial sobre datos estrechos perturba más de lo que ayuda.
4. El vector es minoría de la señal fusionada (BM25+rerank); aunque mejorara, el pipeline no lo notaría.

---

## Estado del repo tras el experimento
- **Producción intacta:** embedder = Qwen3-0.6B base (pgvector sin tocar); todos los flags nuevos
  default OFF; retrieval top_k=10.
- **Código nuevo flag-gated (inerte):** `selective_reform` en config/expansion/retrieve.
- **Artefactos de experimento:** `scripts/ft_*.py`, `scripts/campaign_reform_driver.sh`,
  `scripts/diag_coloquial_routing.py`, `data/eval/ft_pairs.jsonl`,
  `data/eval/results/campaign/REF_*.json`, `data/eval/results/ft_eval*.log`.
- **Modelos FT en disco** (~2.4GB): `models/qwen3-ft-coloquial{,-v2}/` — NO adoptados, borrables.

## Conclusión / recomendación
El residual coloquial NO es cerrable barato con reform / anchoring / fine-tune-chico en este
hardware (8GB GPU, 14GB RAM). Lo que queda como apuesta REAL (no intentada, fuera de hardware):
embedder genuinamente más grande (Qwen3-4B/8B o bge-m3-large) con datos coloquiales REALES (no
sintéticos del mismo LLM). El sistema base es sólido en todo lo demás (dev 37/44, holdout 17/18,
extremo 17/18); el coloquial queda como límite conocido y documentado, no como bug abierto.
