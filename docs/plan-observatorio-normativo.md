# Plan — Observatorio normativo de Transferencias de Mercado (CEN)

**Objetivo del usuario (2026-08-10):** cubrir toda la normativa de su subgerencia del CEN
(Transferencias de Mercado, varios departamentos) más las normas/leyes vinculantes, con un sistema
que las **interconecte** y **detecte y registre automáticamente lo nuevo** (derogaciones,
modificaciones, versiones).

Esto es un **cambio de naturaleza**, no una mejora del RAG actual: el sistema de hoy es un
buscador estático sobre 95 normas de energía. Lo pedido es un **observatorio normativo**: un
corpus vivo, con grafo de vinculaciones y monitoreo de cambios.

---

## 1. Qué YA existe (no rehacer)

| pieza | estado |
|---|---|
| Crawler BCN con Playwright + stealth | ✅ `src/crawlers/norm_detail_crawler.py`, extrae metadata, texto, **vinculaciones** y **versiones** |
| `content_hash` por norma | ✅ ya lo calcula el crawler (sha256 del texto) — base de la detección de cambios |
| Tabla `descargas_estado` | ✅ existe (control de descargas) |
| Tabla `norma_norma(origen,destino,tipo_relacion)` | ✅ existe, **hoy inútil**: 33 filas, todas auto-referencias |
| Tabla `referencias` (5687) | ✅ pero son artículo→artículo *dentro* del corpus; `destino_norma_id` = 0 filas |
| RAG (retrieval + generación + citas) | ✅ maduro: `cita_ok` 261/264, `cita_limpia` 71% |
| `articulos.derogado` | ✅ 2 artículos auto-declarados |

**En curso ahora:** `scripts/scrape_vinculaciones.py` puebla `norma_norma` y deriva
`normas.estado` para las 95 normas actuales. Es el primer eslabón del observatorio.

---

## 2. El corte importante: 3 sistemas, no 1

```
A. CORPUS       que normas entran, y como se descubren     <- HOY: lista fija de 95
B. GRAFO        como se vinculan (modifica/deroga/cita)    <- HOY: vacio (en construccion)
C. MONITOR      que cambio desde la ultima vez             <- HOY: NO EXISTE
```

El RAG actual solo consume A. B y C son nuevos.

---

## 3. Fases propuestas

### FASE 1 — Grafo de vinculaciones (EN CURSO)
Poblar `norma_norma` desde BCN y derivar vigencia.
**Caveat verificado:** `estado` llega `DESCONOCIDO` incluso desde BCN → la vigencia se **deriva**
de `derogada_por`, no se lee.
*Entregable:* saber, de las 95 actuales, cuáles están derogadas y por quién.

### FASE 2 — Alcance real del corpus (DECISIÓN DEL USUARIO, no técnica)
Hoy son 95 normas de energía. "Transferencias de Mercado" necesita definir la frontera:
- ¿Qué departamentos y qué materias cubre exactamente?
- ¿Se incluyen normas **citadas** por las nuestras aunque sean de otra materia (tributario,
  civil, ambiental)? El corpus actual ya cita normas fuera de él.
- ¿Hasta qué profundidad de vinculación? (norma → la que la modifica → la que modifica a esa…)

**Sin esta definición no se puede automatizar el descubrimiento**, y es la decisión que más
condiciona el diseño. Riesgo si se define ancho: el corpus explota y el filtro de dominio del
gate off-topic (calibrado para energía) deja de servir.

*Propuesta:* partir por **cierre transitivo de vinculaciones** desde las 95 semilla (profundidad
1-2), medir cuántas normas nuevas aparecen, y recién ahí decidir.

### FASE 3 — Monitor de cambios
Ya hay `content_hash` y `versiones`. Falta el bucle:
```
1. re-scrapear periodicamente (cron)
2. comparar content_hash y vinculaciones vs lo guardado
3. registrar el DELTA en una tabla de eventos (norma, tipo, fecha, diff)
4. notificar
```
*Entregable:* "el 04.11.2024 la ley 21711 derogó el art. 23 del decreto X, que tu sistema citaba".

⚠️ **Es aquí donde el proyecto entrega valor de verdad**, más que en subir cita_ok.

### FASE 4 — Integración con el RAG
- Filtrar/marcar normas derogadas en retrieval (o citar con advertencia de vigencia).
- Responder preguntas de vigencia y de relación (multi-hop) → recién acá se justifica **G9**
  (eval multi-hop) y eventualmente G5-G10 de GraphRAG.

---

## 4. Riesgos concretos (medidos, no supuestos)

1. **BCN rate-limita.** `obtxml` responde `429 "Service limit has been reached"`; el HTML crudo es
   cáscara JS. Solo funciona vía navegador headless, y **lento** (~15 s/norma + pausa). Con 95
   normas son ~25 min; con miles, horas. El monitor debe ser incremental, nunca full-scan.
2. **El scraping es frágil por diseño.** Depende de selectores del DOM de BCN; si BCN cambia el
   sitio, se rompe en silencio. Necesita test de humo que falle ruidosamente.
3. **Cobertura del gate off-topic.** Está calibrado para energía; al ampliar materias hay que
   recalibrarlo o empezará a rechazar preguntas legítimas.
4. **Escala del RAG.** El corpus actual (2978 artículos) cabe holgado; el `prompt_doc_char_budget`
   ya roza el límite hoy (prompts de 50k chars). Más corpus ⇒ más competencia por el top-10, no
   necesariamente peor, pero hay que re-medir.

---

## 5. Lo que NO recomiendo hacer todavía

- **GraphRAG multi-hop (G5, G6, G8, G10).** Sigue sin justificación: ninguna falla actual es
  multi-hop y el gate (G9) no existe. Con el grafo de FASE 1 poblado, G9 recién se vuelve
  construible — y ahí se decide con datos.
- **Ampliar el corpus antes de la FASE 2.** Sin frontera definida, crecer es acumular ruido.

---

## 6. Siguiente paso concreto

1. Terminar FASE 1 (corriendo).
2. Sobre el grafo poblado: medir el **cierre transitivo** — cuántas normas nuevas aparecen a
   profundidad 1 y 2. Ese número es el insumo para que el usuario defina la frontera (FASE 2).
3. Con la frontera definida, construir el monitor (FASE 3), que es donde está el valor.

---

# PARTE II — Diferenciación y etapas reales (2026-08-16)

Dos observaciones del usuario que cambian el plan:
1. **"Ya hay RAGs que ven normativa"** → indexar Ley Chile está commoditizado; hay que especializarse.
2. **"Hay varias etapas, por ejemplo saber qué scrapear"** → el plan saltaba el DESCUBRIMIENTO.

---

## II.1 Qué es defendible y qué no

| capa | ¿diferencia? | por qué |
|---|---|---|
| Buscar normativa y responder citando | ❌ NO | commodity: cualquiera indexa Ley Chile |
| **Precisión de cita medida** (`cita_limpia` 0.66) | ✅ SÍ | casi nadie mide cuántas de sus citas son CORRECTAS, solo si citó algo |
| **Monitor de cambios** (qué cambió desde la última vez) | ✅ SÍ | BCN da normas sueltas; nadie avisa "esto que citabas cambió" |
| **Inyección determinista** (`glossary_inject`, +16) | ✅ SÍ | portable a cualquier corpus con glosarios |
| **Mapeo norma → obligación → proceso** | ✅✅ **EL FOSO** | nadie fuera del CEN sabe que el art. 3-27 NTCO fija el plazo de TU informe |

**Consecuencia de diseño:** separar desde ya **MOTOR** (retrieval + citas + monitor, portable) de
**DOMINIO** (corpus + mapeo a procesos, específico). Hoy están mezclados.

La pregunta que responde un RAG genérico: *"¿qué dice la norma X?"*
La que responde este: **"¿qué se rompe en mi proceso si cambia la norma X?"**

---

## II.2 ETAPA 0 — DESCUBRIMIENTO (la que faltaba)

No se puede scrapear lo que no se sabe que existe. **Cuatro fuentes, cuatro mecanismos distintos**:

| fuente | qué aporta | mecanismo | estado |
|---|---|---|---|
| **BCN / LeyChile** | leyes, DFL, decretos supremos | Playwright (`norm_detail_crawler.py`) | ✅ funciona, 95 bajadas |
| **CNE** | **NTCO**, resoluciones exentas, informes técnicos | ❌ sin crawler | **FALTA — y es lo más operativo** |
| **SEC** | instructivos, oficios circulares | ❌ sin crawler | falta |
| **CEN (coordinador.cl)** | procedimientos internos, IVTE, minutas | ❌ sin crawler | falta |

**Tres estrategias de descubrimiento, complementarias:**
1. **Por índice/materia** — cada sitio tiene listados por materia. Da el universo, con ruido.
2. **Por vinculación** (ya funciona) — seguir `modifica`/`deroga` desde las semillas. Medido:
   **125 normas nuevas a profundidad 1**. Preciso, pero solo alcanza lo ya vinculado.
3. **Por citación en el texto** — las normas citan otras en su cuerpo (`referencias`: 5687 filas,
   pero hoy `destino_norma_id` = 0 → **hay que resolver esas citas a id_norma**). Es la vía que
   encuentra la normativa que el grafo BCN no declara.

⚠️ **Ninguna sirve sin regla de corte.** Sin ella, seguir vinculaciones arrastró Código Procesal
Penal (47 modificaciones) y Ley de Tránsito (48) al corpus actual.

**Regla de corte propuesta:** entra si (a) regula generación/transmisión/distribución/mercado
eléctrico, **o** (b) modifica/deroga a una que ya está dentro. **No entra por ser citada de paso.**

---

## II.3 Etapas, en orden de dependencia

```
E0  DESCUBRIR      que existe, por fuente        <- FALTA (CNE/SEC/CEN sin crawler)
E1  ACOTAR         regla de corte + poda de 14   <- decision + barato
E2  BAJAR          scrapear lo que paso el corte <- BCN ok, resto por construir
E3  VINCULAR       grafo norma->norma            <- ✅ HECHO (204 aristas)
E4  MAPEAR         norma -> obligacion -> proceso <- EL FOSO, no empezado
E5  MONITOREAR     cron + hash + diff + aviso    <- infra existe, falta cablear
E6  RESPONDER      RAG sobre todo lo anterior    <- ✅ maduro (98.9% cita_ok)
```

**Contraintuitivo pero medido:** E6 (el RAG) está listo y es lo commoditizado. Lo que falta es
E0, E4 y E5 — y **E4 es lo único que nadie más puede copiar**.

---

## II.4 Siguiente paso concreto

1. **Crawler CNE** — sin la NTCO y las resoluciones exentas, el corpus no cubre tu operación diaria.
2. **Resolver `referencias.destino_norma_id`** (5687 filas sin resolver) → habilita descubrimiento
   por citación sin depender de BCN.
3. **Podar las 14 normas ajenas.**
4. **E4 piloto:** tomar UN proceso tuyo (ej. Informe de Valorización de Transferencias Económicas)
   y mapear qué normas/artículos lo obligan, con qué plazo. Si eso funciona en uno, escala al resto.
