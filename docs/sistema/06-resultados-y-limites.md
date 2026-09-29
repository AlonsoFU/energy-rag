# 06 · Resultados y límites (al 2026-09-21)

## Números finales
| | dev (114) | held-out (64) | reales, gold de terceros (16) |
|---|---|---|---|
| artículo correcto (`cita_ok`) | **83 (73 %)** | **62 (97 %)** | **10 (63 %)** |
| `cita_limpia` | 82 | 62 | 10 |
| citas a normas derogadas | 0 | 0 | 0 |
| errores sin ninguna advertencia | ~29 de 32 | 1 de 2 | 5 de 6 |

| recall@10 (artículo correcto entre los 10 que muestra) | **92/114 = 81 %** | **64/64 = 100 %** | **13/16 = 81 %** |

El recall@10 de las 16 reales se midió el 2026-09-28 con `scripts/red_golden.py` (antes era
«NO medido»). Dice dónde está el cuello en las preguntas reales: el buscador encuentra el
artículo en 13 de 16, pero solo 10 se citan bien → **3 de las 6 fallas son de redacción, no
de búsqueda**.

| tiempo por consulta | |
|---|---|
| `--buscar` (solo artículos) | 13 s |
| con respuesta | ~79 s (búsqueda 21.7 s, de ella rerank 21.5 s en CPU) |

## Veredicto
- **Sirve como buscador interno** con una persona que lee la fuente: el artículo correcto llega
  al top-10 en 92 de 114 preguntas de dev, y en 18 de esas queda entre el 6° y el 10° (por eso
  se muestran 10).
- **No sirve para responder solo a terceros.** El error típico es una cita textual de un artículo
  real que no es el que responde: pasa el verificador y no genera aviso.

## Qué se adoptó (2026-09-16 → 21)
| exp | cambio | efecto medido |
|---|---|---|
| #79 | temperatura 0.0 | reproducible: 0 textos distintos en 114 (antes 11 %) |
| #84 | reparar artículos falsos de notas marginales | citas a numeración de ley vieja → 0 |
| #85 | decreto de 1935 marcado derogado | citas a norma muerta 9 → 0 (dev), 4 → 0 (reales) |
| fix | parser: el monitor ya no re-rompe el corpus | test en ambos sentidos |
| #83 | reatribución + aviso «SIN CITA VERIFICADA» | held-out limpia 59 → 61, 0 pérdidas |
| #86 | 1 muestra en vez de 3 | 0 pérdidas, ~12 % más rápido |
| #69a | limpieza de notas BCN | dev 80 → 83, limpia 78 → 82 |
| #88 | reranker GPU solo en `--buscar` | búsqueda 21.5 → 2.9 s, orden idéntico |
| UI | fuentes primero, respuesta como resumen | — |

## Qué se probó y NO funcionó
| exp | idea | resultado |
|---|---|---|
| #82 | juez local «¿la cita responde la pregunta?» | detecta 3 de 28 errores; descartado |
| #87 | modelo más grande (27B denso) | no viable en este hardware; no concluyente (2 respuestas completas) |
| #88 | reranker en GPU para el modo con respuesta | desplaza al LLM (49 → 43 capas en GPU) |
| #88b | reranker fp16 en GPU | cambia el orden en 73/194 y no libera al LLM |
| #80 / #81 | «el ruido es num_ctx» / «es un commit» | falsadas: era el corpus cambiado por el monitor |
| antes | HyDE, concept_inference, selective_reform, prompts enfáticos, RK1 (Qwen3-Reranker) | planos o negativos |
| — | bajar `ollama_num_ctx` a 16384 para ganar velocidad | descartado sin medir: puede truncar prompts en silencio y no gana precisión |

## Por qué falla (estado final, `diag_donde_falla`)
31 fallas de dev: **18 de búsqueda** (el artículo correcto nunca llega a los 10) y **13 de
redacción** (llega, pero el modelo cita otro; en ninguna estaba en el 1° lugar; mediana 5°).
La búsqueda coloquial es el cuello: «¿quién termina pagando esas torres y cables grandes?» →
Art. 115 LGSE «Pago de la Transmisión», sin palabras en común.

## Trabajo futuro, por impacto en precisión
1. **Afinar el buscador denso** con pares pregunta coloquial → artículo + negativos difíciles
   (los que hoy salen por error). Evidencia en legal: nDCG@10 5.40 → 14.67 (CLERC). Riesgo:
   pares escritos por el asistente → sobreajuste; medir con las 80 públicas. Días de trabajo.
   `ft_pairs.jsonl` existe pero requiere autorización del usuario.
2. **Eval v2:** corregir 4 gold en norma derogada, sumar SEC arts. 127 y 217, etiquetar más de
   las 64 preguntas reales sin gold (hoy 16 → apuntar a ~100).
3. Alertas cuando algo falla (monitor, cola, GPU): hoy todo queda en archivos.
4. Reranker en GPU también con respuesta: requiere liberar VRAM del LLM sin tocar su contexto.
