# Plan — Campaña de CHUNKING (reglas 1-4 del estándar legal-RAG)

Fecha: 2026-07-07. Arranca +2h (usuario duerme). Autónomo, checkpointeado, no-destructivo.

## Objetivo
Estudiar TODOS los artículos (2978) y barrer estrategias de chunking para las 4 reglas del
estándar legal-RAG, hallando el óptimo de cada una **medido** (gold∈top5/top10 sobre
coloquial 39 + dev 44), sin tocar la DB hasta elegir ganador.

## Estándar (investigado 2026-07-07, ver handoff)
1. **section-aware** — partir por jerarquía propia (art/inciso), no por tamaño.
2. **una provisión = un chunk** — no fundir 50 defs; no partir a mitad.
3. **context enrichment (header-path)** — anteponer ruta `[norma > título > art N]`.
4. **late/cross-ref** — embeber con contexto de remisiones (difícil; versión ligera).

Ref: LegalBench-RAG (2408.10343), Reliable Retrieval Large Legal (2510.06999), Edtek.

## Método (no-destructivo)
Harness `scripts/exp_chunk_sweep.py`: para cada estrategia (chunker × contexto),
re-chunkea en MEMORIA desde `articulos.texto`, embebe con 4B (ollama, MRL-1024 = producción),
mide rank del gold. Checkpoint por estrategia en `data/eval/results/chunk_sweep/result.json`.
Regla de oro: el screen MIENTE → el ganador se confirma end-to-end (cita_ok) antes de adoptar.

## Grid a barrer
Chunkers (sobre art.texto):
- `asis` (fragmentos actuales de la DB = BASELINE)
- `whole` (1 artículo = 1 fragmento)
- `glossary` (R2: glosarios → 1 def/frag; resto whole)
- `inciso` (R1 fino: parte cualquier art por marcadores a./1./incisos; fallback whole)
- `slide1000_200` (R1 estándar: ventana 1000c solape 200)
- `slide500_100` (R1 fino)

Contexto (regla 3), aplicado al texto embebido:
- `ctx_none` (texto crudo)
- `ctx_light` (`[norma/numero] texto`)
- `ctx_path` (`[norma > título > art N] texto`)

Combos priorizados (12): baseline(asis+light) · whole×{none,light,path} ·
glossary×{light,path} · inciso×{light,path} · slide1000_200×{light,path} · slide500_100×light.

## Orden de fases (cada una para y mide)
- **F1 — regla 2 (glossary)**: confirmar el lift del split de definiciones. Barato, ya hay parser.
- **F2 — regla 1 (section)**: inciso vs slide1000 vs slide500 vs whole → mejor granularidad general.
- **F3 — regla 3 (context)**: none vs light vs path sobre el mejor chunker de F2.
- **F4 — regla 4 (cross-ref)**: versión ligera (append remisión) si F1-3 dejan margen.
- **F5 — combinar** mejores de cada regla, medir juntos (¿interactúan?), confirmar end-to-end.

## Criterio de éxito
Mejora neta gold∈top5 en coloquial (frente) + dev SIN regresión, confirmada end-to-end.
Todo flag-gated. Documentar ADR + handoff al adoptar. Diseñado para escala (regla, no parche).

## Fallos-objetivo (diagnóstico previo)
- 4 dev pool-miss: 2× art225 def enterrada (→R2), 1× SEC función, 1× Panel función (→grafo, otra campaña).
- 11 coloquial reranker-miss: gold en pool rank profundo (→ R2/R3 lo suben con señal nítida).
