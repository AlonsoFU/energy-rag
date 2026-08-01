# Backlog de mejoras — cola por hacer

Deriva de `docs/research-improvements-2026-07-31.md` (deep-research verificado 3-votos).
Origen arquitectura: `docs/handoff-2026-07-31.md`.

## Protocolo (OBLIGATORIO por experimento)
1. Flag-gated, default OFF.
2. Medir dev + holdout (caza overfit) + no-regresión vs config vigente.
3. Al terminar: mover el item a **HECHO** abajo con el resultado medido (Δ cita_ok dev/coloq/holdout).
4. Si da **MEJOR** sin regresión → se adopta y **reemplaza la arquitectura** (config vigente en
   `CLAUDE.md` "Estado actual" + `.env`/flags). Si NO mejora → queda en **PROBADO — NO repetir**
   con el número, para no rehacerlo.
5. Documentar ADR/handoff junto al cambio (no al final de sesión).

Estados: `[ ]` pendiente · `[~]` en curso · `[x]` hecho-adoptado · `[-]` probado-descartado.

## Cola (orden: mínimo esfuerzo → máximo)

- [ ] **M1 · Rerank 50-100 candidatos** (no top-10). 1 parámetro (`retrieval_pool_depth` al rerank).
  GPU: ✅ trivial. Ataca: art 225 enterrado + residuos coloquiales bajo rank 10. Fix gratis. HACER YA.
- [ ] **M2 · 1 def = 1 fragmento + parent-doc** para art 225. Preprocesamiento, sin VRAM.
  Ataca: 4/8 fallas dev (cluster glosario LGSE). Preferir sobre MoG (router entrenado).
- [ ] **M3 · STARA** — aumentar cada art con defs+refs+padre antes de indexar. CPU+LLM local.
  Hacer si M2 no cierra el cluster art 225.
- [ ] **M4 · Step-back query rewriting** — complemento liviano del alias-map (NO reemplazarlo).
  Ataca: residuos coloquiales (torres vida útil, planta solar). GPU: ✅ 1 reescritura qwen3:30b.
- [ ] **M5 · SAC** (resumen de norma prepend a cada chunk) — contra cross-doc mismatch.
  ⚠️ corpus ~78 normas puede no necesitarlo (menos presión DRM que 362) → medir si mueve cita_ok
  o solo agrega latencia. Adopción NO automática.
- [ ] **M6 · ColBERT rerank** (late-interaction sobre pool 100-500). Experimental, solo si M1-M3
  no bastan. ⚠️ pgvector sin MaxSim indexado → solo como rerank de pool acotado, NO retrieval 1ª
  etapa. Escala indexada necesitaría VectorChord (complejidad operacional — evaluar aparte).

## NO hacer (research lo desaconseja — dañan cita_ok)
- [-] **HyDE / multi-query** — alucinan cifras, desvían embedding, dañan retrieval preciso (0-3).
- [-] **DMQR-RAG fan-out completo** — su rama pseudo-answer ES HyDE. A lo sumo usar keyword +
  core-content dentro del union del alias-map.
- [-] **Mix-of-Granularity (router entrenado)** — requiere datos etiquetados + entreno. Usar M2 simple.

## HECHO / adoptado
- (vacío — se llena al ejecutar la cola)

## PROBADO — NO repetir (ya en CLAUDE.md + architecture-status.md)
- 8B embedder (trade-off), citation_repair, concept_inference, doc2query, fine-tune 0.6b, HyDE,
  selective_reform, gemma2:27b (roto). Detalle: `CLAUDE.md` + `docs/architecture-status.md`.
