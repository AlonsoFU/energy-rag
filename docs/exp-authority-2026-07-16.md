# EXP autoridad/jerarquía en el ranking (2026-07-16) — gap #4

**Hipótesis:** la jerarquía normativa chilena (LEY≡DFL≡DL > DECRETO > RESOLUCIÓN)
se EXTRAE (`src/extraction/norm_rank.derive_rank`) pero nunca pesó el ranking.
Boostear el tier alto podría subir cita_ok al preferir la norma más autoritativa.

**Implementación (flag `authority_rank_boost`=β, default 0.0 OFF):**
- `src/pipelines/retrieve.py`: `_norma_ranks()` (cacheado, rango por TÍTULO vía
  `derive_rank` — el `tipo` de la DB no es confiable) + `authority_boost()`.
- Aplicado tras graph_boost, antes de truncar a top_k: `score·(1+β·(rank-2))`.
  LEGAL(3)→×(1+β), DECRETO(2)→×1, RESOLUCIÓN(1)→×(1-β).
- Runner: `scripts/exp_authority.py` (pipeline prod real, AdaptiveRetriever →
  generate_answer, gen = ollama/qwen3.5:9b prod). Barrido β∈{0.0, 0.1, 0.2}.

**Resultado — PLANO, cero efecto en cita_ok:**

| set | n | β0.0 | β0.1 | β0.2 |
|---|---|---|---|---|
| coloquial | 39 | 25 | 25 | 25 |
| dev | 44 | 34 | 34 | 34 |

Idéntico en todo β. No mueve, no regresiona.

**Por qué (caveat):** 72/95 normas (76%) son tier LEGAL — la LEY eléctrica 258171
domina el corpus. Los pools recuperados son casi mono-tier → multiplicar todo el
pool por (1±β) NO reordena nada. La autoridad solo desempata pools que MEZCLAN
tiers, situación rara aquí. Consistente con la regla de oro: el retrieval-side no
convierte a cita_ok.

**A escala** (más decretos/resoluciones/otras leyes) el corpus se vuelve
multi-tier y el boost SÍ podría importar → por eso el flag queda (OFF), no se borra.

**Decisión:** flag `authority_rank_boost` permanece OFF (0.0). Infra table-stakes
lista para cuando el corpus crezca; hoy no aporta a la métrica.

Dist rangos (95 normas): 72 LEGAL / 18 DECRETO / 5 RESOLUCIÓN.
