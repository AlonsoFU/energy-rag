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
- **Baseline corregido estimado ~86%; CONFIRMADO con re-run sobre eval v2 = 234/279 = 84%**
  (8 de 15 recuperables flipearon). Las otras 14 = retrieval real (glosario-enterrado); 5 = acrónimos.
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

## Cierre #1/#2 (2026-08, audit otros evals + vigencia)
- **def_fragments en DEV** (`scripts/exp_deffrag_dev.py`): OFF 36/44 → ON 37/44 (gano 1 "seguridad
  de servicio", perdió 0), McNemar p=1.0 = FLAT. Ni en glosario puro (dev = cluster art-225 LGSE)
  convierte. El art-225 ya entra al top-10 (no es recall); es GEN y la def focalizada no ayuda a
  citar confiable. **def_fragments MUERTO en todos lados.**
- **#1 audit:** dev/coloquial/holdout NO subestimados como balanced_v2 (ya traen also_gold; art-225
  se recupera bien). El −22 era específico de los golds auto-generados multi-norma de balanced_v2.
- **#2 vigencia (D1):** `normas.estado` = 93/95 DESCONOCIDO/null → gap de datos TOTAL. Requiere
  scrape BCN (proyecto de datos, no experimento). Alto valor legal, scope grande.
- **FRENTE DEFINICIONES/RETRIEVAL DEFINITIVAMENTE CERRADO.** Sistema real ~84%, sano. Próximo
  valor real = vigencia (scrape BCN) o escala, NO más ingeniería de retrieval/gen.

---

## ⚠️ CORRECCIÓN (2026-08-05) — el frente NO estaba cerrado: `glossary_inject` +16

Todo lo de arriba concluía "FRENTE RETRIEVAL DEFINITIVAMENTE CERRADO, sistema ~84%, próximo valor
= vigencia o escala". **Eso resultó FALSO.** Un experimento más lo movió 5.7 puntos.

### Resultado (`scripts/exp_glossary_inject.py`, McNemar pareado, balanced_v2_clean in_domain 279q)
```
OFF 233/279 (83.5%)  ->  ON 249/279 (89.2%)
gano 16, perdio 0
McNemar p=0.0000  (SIGNIFICATIVO)
```
**16 ganadas, CERO pérdidas.** Mayor WIN de retrieval de toda la campaña (embedder 4B fue +3,
gate AND +4). ADOPTADO: flag `glossary_inject` default ON (`src/core/config.py`).

Ganadas: Coordinador · Superintendencia · Ministerio · Cliente · Titular · Solicitante · Proyecto ·
Actividad · Ajustes · Estado Deteriorado · Infracciones {gravísimas, graves ×2, menos graves,
leves ×2 fraseos}.

### Qué es
Arista determinista término-glosario→artículo padre. En query de definición, si el concepto matchea
EXACTO un término de `fragmentos_definicion`, se garantiza el artículo padre en el top-k (inyectado
al tope si falta, sin desplazar nada más). Es GraphRAG-1-salto bien hecho, mismo patrón que
`alias_map`. Piezas: `vectorstore.def_exact`, `retrieve._definition_concept`, bloque de inyección
en `SimpleRetriever.retrieve` paso 6c.

### Por qué funcionó donde def_fragments y RK1 fallaron
- **def_fragments (RRF)** competía por score y DESPLAZABA buenos resultados → net flat.
- **RK1 (Qwen3-Reranker)** no arregla el sesgo: ambos cross-encoders prefieren el artículo FUNCIONAL
  sobre el DEFINITORIO (Coordinador: funcional 258171/212-1 = 0.9985 vs def 250604/13 = 0.981).
- **glossary_inject** no pelea con el score: pasa por al lado con un match exacto de estructura.

### Lecciones (las importantes)
1. **Contra un ordenador sesgado, inyección determinista > mejor ordenador.** El muro del reranker
   era real, pero la salida no era otro modelo — era usar la estructura de datos.
2. **"Frente agotado" era una conclusión sobre los experimentos hechos, no sobre el problema.**
   5 negativos seguidos hicieron parecer que no quedaba nada; faltaba el que atacaba la causa.
3. **El diagnóstico subestimó el alcance:** se predijeron 6 fallas de glosario, ganó 16. También
   arregló casos clasificados como "ranking" (gold en el pool pero enterrado por el reranker) →
   los buckets del diagnóstico no eran independientes.
4. **Bug de infra encontrado:** el resume del script leía `c["q"]` en vez de `c["query"]`, con el
   KeyError tragado por `except: pass` → regeneraba las 279 desde cero en silencio. Fix en `a86a594`.
   *Un `except: pass` sobre lógica de resume esconde horas de cómputo perdido.*

### Estado real tras esto
- cita_ok in_domain: **89.2%** (249/279). Rechazo off-domain/off-corpus: 100%.
- Residual (30 fallas): acrónimos (D2), ~5 coloquiales (muro semántico), gen-fails, golds rotos (E0c).
- Siguiente en cola: `docs/backlog-mejoras.md` FASE A item 2 (M1 re-test pool=100, **re-diagnosticar
  primero** — glossary_inject ya se comió parte de los 13 ranking-fails).

---

## M1 pool 50→100: MUERTO DEFINITIVO (2026-08-06) + 2 bugs de generación encontrados

### M1 (`scripts/exp_m1_paired.py`, pareado, glossary_inject ON)
```
OFF 252/279  ->  ON 252/279   (gano 0, perdio 0)
McNemar p=1.0000  (flat)   279/279 pares, 0 errores
```
41 top-10 cambiaron con pool=100 y **ninguno convirtió**. Cero flips en 279 queries no es "poca
señal": es plano. El gold NO está escondido en rank 50-100. No re-probar sin hipótesis nueva.

Se escribió script nuevo en vez de usar `exp_m1_pooldepth.py`: ese compara contra
`e0_baseline/result.json` (pool=50, glossary_inject OFF) — comparar contra un baseline obsoleto
mezclaría el efecto del pool con el del inject y el flicker del LLM (el error que contaminó M2).

### Bug 1 — overflow de num_ctx → deadlock → FALSOS NEGATIVOS en el eval
Prompts de queries "Costo de Falla": 48-50k chars ≈ 15.0-15.6k tokens. Con `max_tokens=2000` de
salida da ~17.6k > `num_ctx=16384` → el sampler se cuelga hasta el timeout de litellm
(300s × 3 reintentos = **900s perdidos por query**).
Lo grave no es el tiempo: `gen()` devolvía `False` al agotar reintentos, así que **un timeout se
anotaba como `cita_ok=False`**. Mismo patrón que el eval sucio: el sistema medía mal, no fallaba.
Fix: `ollama_num_ctx=32768` (VRAM verificada 3090: 21510/24576 MiB) + `gen()` devuelve `(ok, err)`
y los `err` se EXCLUYEN del McNemar.

### Bug 2 — sin cap de salida, el generador se desboca (lo destapó el fix del bug 1)
`llm.py` DESCARTA `max_tokens` para ollama (`kwargs.pop`), así que no había `num_predict`: ollama
genera hasta LLENAR el contexto. Con `num_ctx=16384` el tope quedaba en ~1.3k tokens **por
accidente**; al subirlo a 32768 la salida quedó suelta hasta ~17k tokens → 436s → timeout.
*El fix del bug 1 causó el bug 2.*

Causa de fondo (peor que el timeout): con `think=False` el modelo razona en el CUERPO de la
respuesta y entra en **loop de deliberación**. Medido en "qué es Superintendencia":
```
eval_count=2000  done_reason=length   <- seguia deliberando al cortarse
"...Pero necesito verificar si hay una definicion mas especifica para el contexto electrico..."
28 citas extraidas, mayoria DUPLICADAS
```
Fix aplicado: `ollama_num_predict=2000`. Verificado que el bug viejo documentado en `llm.py`
("num_predict trunca la salida") NO se reproduce en esta versión: 2000 tokens limpios con ctx 32768.

### Consecuencias (más importantes que M1)
1. **El baseline real subió 249 → 252/279 (89.2% → 90.3%)**: 3 queries que se colgaban y se
   contaban `False` ahora generan. El sistema estaba mejor de lo que decía la métrica.
2. **Riesgo de métrica NUEVO (item E3):** `cita_ok` da True si CUALQUIER cita pega. Una respuesta
   que dispara 28 citas acierta por VOLUMEN, no por precisión. Hay que auditar cuántos de los 252
   aciertos vienen de respuestas con muchas citas. *La métrica puede estar inflando.*
3. **GEN8:** el cap evita el timeout pero la respuesta sigue siendo un monólogo truncado. El
   generador no converge — arreglo real es de prompt/formato, no de tope de tokens.

### Lección
Perseguir un cuelgue de infraestructura rindió más que el experimento que lo destapó. Y un fix
puede destapar el bug siguiente: subir el techo (num_ctx) sin acotar el contenido (num_predict)
movió el problema en vez de resolverlo.

### Caveat de honestidad sobre este run
El run abarcó cambios de config a mitad de camino (idx 0-229 con ctx=16384, 230+ con 32768).
El diseño **pareado** protege el veredicto —ambos brazos ven la misma config en cada query— pero
los totales ABSOLUTOS de esta corrida no son comparables con otras. El 252/279 se debe re-confirmar
en una corrida limpia con la config final (ctx 32768 + num_predict 2000).

---

## E3 — auditoría del efecto escopeta (2026-08-07): la métrica SÍ está sana

Sospecha (tras ver 28 citas duplicadas en una respuesta): `cita_ok` marca True si CUALQUIER cita
pega → una respuesta que rocía citas podría acertar por VOLUMEN. Si eso fuera masivo, el 252/279
estaría inflado y todo el plan estaría optimizando contra un número falso.

### Resultado (`scripts/exp_e3_shotgun.py`, 279 in_domain, config vigente)
```
cita_ok (ALGUNA pega):   253/279  (90.7%)
hit_first (la 1a pega):  243/279  (87.1%)
citas por respuesta: media 13.1  unicas 4.2  max 60
precision media EN HITS: 0.43   (mediana 0.33; 143/253 hits con <0.5)
```
**Veredicto: la métrica NO infla.** Solo **11 queries (3.9%)** aciertan por una cita no-primera, y
10 de esas es la 2ª. El 252-253/279 es defendible. *A diferencia del eval sucio (−22) y de los
timeouts contados como False, acá la sospecha NO se confirmó.*

**Pero sí hay un problema de CALIDAD de cita:** precisión media 0.43 — de 4.2 artículos citados,
menos de la mitad son correctos. En contexto legal, citar normas equivocadas junto a la correcta
es dañino aunque `cita_ok` dé True. La causa es GEN8 (el loop), no la métrica.

### Descomposición REAL de las 26 fallas (`scripts/diag_refusals.py`)
```
RETRIEVAL (gold nunca llego al pool): 16
GEN       (gold en el pool, no lo uso): 10   <- 6 de ellas con gold en RANK=0
19 de las 26 son RECHAZOS ("no encuentro la norma"), no citas erradas
```
Las 16 de retrieval son términos que el extractor de glosario NO capturó (`def_exact`=None para
los 3 fraseos): Acometida, Tránsito, TON, DIP, DIA, Gas licuado, Vehículo, Empresa distribuidora,
Reposición. **No es "2 siglas" como decía el backlog: es el extractor incompleto** → D2 AMPLIADO
es el item de mayor ROI pendiente (mismo patrón que rindió +16 con glossary_inject).

Las 10 de gen, con **6 con el gold de PRIMERO**, son GEN8 puro: el modelo delibera (en inglés:
*"Okay, let's tackle this query..."*), cita 10-12 artículos y termina rechazando pese a tener el
artículo correcto en la posición 0.

### Falso positivo de análisis (anotado para no repetirlo)
En la auditoría de golds se concluyó primero que 8 golds "NO EXISTÍAN" en la DB. **Era error del
query de auditoría**, que comparaba `numero` exacto sin normalizar: en la DB son `2º D`, `7°`, `4º`
—con º/°— y el eval sí normaliza vía `_normalize_art`. Re-auditado con normalización:
**0 inexistentes, 23 válidos, 3 dudosos** (Vehículo 1155887/7 = artículo modificatorio).
Las fallas son REALES. *Auditar el eval requiere usar las MISMAS normalizaciones que el eval.*

### Gap de infra cerrado
Ningún eval de la campaña guardaba el TEXTO de las respuestas, solo el booleano `ok` — por eso no
se pudo auditar nada retroactivamente y hubo que regenerar. `exp_e3_shotgun.py` ya persiste `text`
y `cits` por query. Adoptar ese patrón en los evals futuros.

---

## D2 pre-análisis (2026-08-07): auditar el gold ANTES de construir el fix

Iba a extender el extractor de glosario para los 16 términos que E3 marcó como fallas de retrieval.
Antes de escribir código, se revisó **qué dice realmente el artículo gold**. Resultado: **solo 15
de las 26 fallas son atacables; 11 son imposibles.**

### El corte que manda: ¿el gold DEFINE o solo MENCIONA?
```
DEFINE (arreglable):  15   TON, DIP, DIA, Reposicion, Informe Definitivo x3,
                           Infracciones graves, Transito x3
MENCIONA (imposible): 11   Gas licuado x3, Acometida x3, Vehiculo x3,
                           Empresa distribuidora x2
```

Ejemplos de gold que solo MENCIONA:
```
Acometida   1160108/16  "...diagrama georreferenciado de la acometida a la subestacion"
Vehiculo    1155887/7   "...tratandose de vehiculos motorizados livianos, medianos y pesados"
Gas licuado 29819/2 D   "...envases, aparatos e instrumentos de gas licuado"
Emp. distr. 250604/13   "...clientes no sometidos a regulacion de precios o empresas distribuidoras"
```
Búsqueda en los **2960 artículos** con 5 patrones (`TERM:`, `se entiende por`, `TERM es/será`,
`se denomina`, `definición de`): **0 definiciones reales** de esos 4 términos. Los pocos matches de
`TERM es/será` son frases incidentales ("La Empresa Distribuidora **será responsable de** obtener
las medidas..."), no definiciones.

**Conclusión: el sistema RECHAZA CORRECTAMENTE y el eval lo penaliza.** No hay nada que arreglar en
el sistema para esas 11 — hay que arreglar el eval (E0c).

### Métrica corregida
```
cita_ok reportado:                 253/279 = 90.7%
descontando las 11 imposibles:     253/268 = 94.4%
contando el rechazo como acierto:  264/279 = 94.6%
```

### El hueco REAL de D2: formato leyenda de variable
Lo que sí falta capturar (`build_def_fragments.py` no lo maneja):
```
250604/53   "TON      : Tiempo medio acumulado en que la Unidad Generadora ... en operacion"
250604/31   "Donde:  DIP: Menor disponibilidad media anual del Insumo Principal ..."
```
Formato `SIGLA : descripción`, típicamente tras "Donde:" en artículos con fórmulas. Ataca ~7
queries (TON ×2, DIP ×2, DIA ×3). Barato y con el patrón ya validado (glossary_inject +16).

### Lección (4ª vez que el eval es parte del problema)
Historial: eval sucio (−22, E0b) · timeouts contados como False (−3) · golds mención-vs-definición
(−11). **Auditar el gold ANTES de construir el fix.** Esta auditoría de ~20 min evitó escribir un
extractor para 9 términos, de los cuales 4 simplemente no existen en el corpus.
