================================================================================
ARQUITECTURA HÍBRIDA: Keywords + Embeddings + Información Experta
================================================================================

## PREGUNTA 1: ¿Cómo decidir entre Keywords y Embeddings?

RESPUESTA CORTA: NO eliges uno u otro - usas AMBOS en paralelo y fusionas

════════════════════════════════════════════════════════════════════════════


## ESTRATEGIA 1: Pipeline Secuencial (Filtro + Re-ranking)

┌──────────────────────────────────────────────────────────────────────────┐
│ PASO 1: Keywords (filtrado rápido)                                      │
│   Input:  "planta incrementó su capacidad instalada"                    │
│   Extrae: ['planta', 'capacidad', 'instalada']                          │
│   Busca:  Normas con esas keywords                                      │
│   Output: 200 normas candidatas (de 2,031)                              │
│   Tiempo: 50ms                                                           │
├──────────────────────────────────────────────────────────────────────────┤
│ PASO 2: Embeddings (re-ranking semántico)                               │
│   Input:  200 normas candidatas                                         │
│   Calcula: Similitud semántica de cada una vs query                     │
│   Re-rankea: Por score semántico                                        │
│   Output: Top 10 normas más relevantes                                  │
│   Tiempo: 30ms                                                           │
├──────────────────────────────────────────────────────────────────────────┤
│ TOTAL: 80ms, mejor precisión que solo keywords                          │
└──────────────────────────────────────────────────────────────────────────┘

VENTAJAS:
✅ Rápido (keywords filtra mayoría de irrelevantes)
✅ Preciso (embeddings refina los candidatos)
✅ Mejor de ambos mundos

CÓDIGO:
```python
def buscar_hibrido_secuencial(query, normas, top_k=10):
    # PASO 1: Filtrado con keywords (rápido)
    candidatos = buscar_keywords(query, normas, top_n=200)

    # PASO 2: Re-ranking con embeddings (preciso)
    if len(candidatos) == 0:
        return []

    query_emb = model.encode([query])
    candidatos_embs = embeddings[candidatos['indices']]
    scores_semanticos = cosine_similarity(query_emb, candidatos_embs)[0]

    # Combinar y retornar top 10
    candidatos['score_semantico'] = scores_semanticos
    return candidatos.nlargest(top_k, 'score_semantico')
```

USO: Cuando tienes >5K normas y quieres velocidad + precisión


## ESTRATEGIA 2: Búsqueda Paralela + Fusión de Scores

┌──────────────────────────────────────────────────────────────────────────┐
│ CAMINO A: Keywords                                                       │
│   "planta capacidad" → 50 normas con scores [0.9, 0.8, 0.7, ...]       │
├──────────────────────────────────────────────────────────────────────────┤
│ CAMINO B: Embeddings                                                     │
│   embedding(query) → 50 normas con scores [0.85, 0.82, 0.80, ...]      │
├──────────────────────────────────────────────────────────────────────────┤
│ FUSIÓN:                                                                  │
│   score_final = α * score_keywords + (1-α) * score_embeddings           │
│   α = 0.3 (favorece embeddings)                                         │
│                                                                          │
│   Norma D.62:                                                            │
│     Keywords:   0.4 (bajo, no hay overlap exacto)                       │
│     Embeddings: 0.9 (alto, entiende contexto)                           │
│     FINAL:      0.3*0.4 + 0.7*0.9 = 0.75 ✅ Alta                        │
└──────────────────────────────────────────────────────────────────────────┘

CÓDIGO:
```python
def buscar_hibrido_paralelo(query, normas, top_k=10, alpha=0.3):
    # Ejecutar AMBAS búsquedas en paralelo
    scores_keywords = buscar_keywords_con_scores(query, normas)
    scores_embeddings = buscar_embeddings_con_scores(query, normas)

    # Normalizar scores a [0, 1]
    scores_kw_norm = normalize(scores_keywords)
    scores_emb_norm = normalize(scores_embeddings)

    # Fusión lineal
    scores_finales = alpha * scores_kw_norm + (1 - alpha) * scores_emb_norm

    # Retornar top K
    return top_k_normas(scores_finales, k=top_k)
```

VENTAJAS:
✅ No pierdes buenos resultados de ningún método
✅ Balanceas precisión vs explicabilidad
✅ Puedes ajustar α según necesidades

CÓMO ELEGIR α:
```
α = 0.0 → Solo embeddings (máxima precisión, caja negra)
α = 0.3 → Favorece embeddings (recomendado)
α = 0.5 → Balance 50/50
α = 0.7 → Favorece keywords (más explicable)
α = 1.0 → Solo keywords (transparente pero menos preciso)
```

USO: Cuando quieres lo mejor de ambos métodos


## ESTRATEGIA 3: Adaptativo (según confianza)

┌──────────────────────────────────────────────────────────────────────────┐
│ DECISIÓN DINÁMICA basada en características del query                   │
├──────────────────────────────────────────────────────────────────────────┤
│ SI query usa terminología técnica exacta:                               │
│   → Usar KEYWORDS (más confiable)                                       │
│   Ejemplo: "decreto 62 transferencias potencia"                         │
│   Keywords: 0.95 ✅                                                      │
│   Embeddings: 0.88 (innecesario)                                        │
├──────────────────────────────────────────────────────────────────────────┤
│ SI query usa lenguaje natural/sinónimos:                                │
│   → Usar EMBEDDINGS (entiende contexto)                                 │
│   Ejemplo: "planta incrementó capacidad"                                │
│   Keywords: 0.2 ❌                                                       │
│   Embeddings: 0.9 ✅                                                     │
├──────────────────────────────────────────────────────────────────────────┤
│ SI query tiene términos mixtos:                                         │
│   → Usar HÍBRIDO (fusión)                                               │
│   Ejemplo: "decreto sobre plantas eléctricas"                           │
│   Keywords: 0.6 (detecta "decreto")                                     │
│   Embeddings: 0.8 (entiende "plantas eléctricas")                       │
│   Fusión: Mejor resultado                                               │
└──────────────────────────────────────────────────────────────────────────┘

CÓDIGO:
```python
def buscar_adaptivo(query, normas, top_k=10):
    # Analizar características del query
    tiene_num_decreto = bool(re.search(r'(decreto|ley|resolución)\s*\d+', query.lower()))
    tiene_keywords_exactas = len(extraer_keywords_tecnicas(query)) > 2
    es_natural = not (tiene_num_decreto or tiene_keywords_exactas)

    # Estrategia adaptativa
    if tiene_num_decreto:
        # Query específica → Solo keywords (rápido y exacto)
        return buscar_keywords(query, normas, top_k)

    elif es_natural:
        # Query natural → Solo embeddings (entiende contexto)
        return buscar_embeddings(query, normas, top_k)

    else:
        # Query mixta → Híbrido (mejor de ambos)
        return buscar_hibrido_paralelo(query, normas, top_k, alpha=0.3)
```

VENTAJAS:
✅ Usa el método más apropiado para cada caso
✅ Optimiza velocidad (keywords solo cuando basta)
✅ Optimiza precisión (embeddings cuando necesario)

EJEMPLOS:
```
Query: "decreto 62"
  → Detecta número decreto
  → Usa KEYWORDS (instantáneo, 100% preciso)

Query: "operador del sistema eléctrico"
  → Detecta lenguaje natural
  → Usa EMBEDDINGS (entiende "operador"="coordinador")

Query: "decreto sobre suficiencia"
  → Detecta mixto (decreto + concepto)
  → Usa HÍBRIDO (keywords + embeddings)
```


════════════════════════════════════════════════════════════════════════════


## PREGUNTA 2: ¿Cómo incorporar información experta (notas, anotaciones)?

RESPUESTA CORTA: Enriquecer embeddings + metadata + re-ranking experto

════════════════════════════════════════════════════════════════════════════


## USO 1: Metadata para Filtrado Previo

```python
# Estructura de norma ENRIQUECIDA con información experta
{
    "id_norma": "1037065",
    "tipo": "DECRETO",
    "numero": "62",
    "titulo": "APRUEBA REGLAMENTO DE TRANSFERENCIAS DE POTENCIA...",
    "temas_detectados": ["POTENCIA", "GENERACION", "SSCC"],

    # ← INFORMACIÓN EXPERTA AGREGADA
    "metadata_experta": {
        "relevancia_potencia": 10,  # Score 1-10 dado por experto
        "casos_uso": [
            "Transferencias de suficiencia",
            "Remuneración por disponibilidad",
            "Potencia de punta"
        ],
        "conceptos_clave": [
            "suficiencia",
            "potencia firme",
            "valorización"
        ],
        "normas_relacionadas_experto": ["D.113", "Ley 20936"],
        "notas_experto": "Norma principal para potencia. Aplica a generadores >20MW",
        "vigencia_real": "vigente_critica",  # vs "vigente_poco_usada"
        "complejidad": "alta",
        "frecuencia_uso": 150  # veces citada por expertos
    }
}
```

CÓMO USAR:
```python
def buscar_con_metadata_experta(query, caso_tipo="potencia"):
    # PASO 1: Filtrar por metadata experta
    if caso_tipo == "potencia":
        candidatos = normas[
            (normas['metadata_experta.relevancia_potencia'] >= 7) |
            (normas['metadata_experta.frecuencia_uso'] >= 50)
        ]
        # Reduce búsqueda de 2,031 → 150 normas relevantes

    # PASO 2: Búsqueda semántica en candidatos filtrados
    resultados = buscar_embeddings(query, candidatos, top_k=20)

    # PASO 3: Re-ranking con metadata experta
    for r in resultados:
        bonus_vigencia = 0.1 if r['vigencia_real'] == 'vigente_critica' else 0
        bonus_frecuencia = min(r['frecuencia_uso'] / 1000, 0.2)
        r['score_final'] = r['score_semantico'] + bonus_vigencia + bonus_frecuencia

    return resultados.sort_by('score_final', descending=True)[:10]
```

VENTAJAS:
✅ Expertos guían qué normas son realmente importantes
✅ Evitas normas técnicamente relevantes pero poco usadas
✅ Incorporas conocimiento del dominio


## USO 2: Embeddings Enriquecidos con Notas Expertas

En lugar de solo embedding del título, combinas con información experta:

```python
def generar_embedding_enriquecido(norma):
    # Texto base
    texto_base = norma['titulo']

    # Enriquecer con información experta
    if 'metadata_experta' in norma:
        # Agregar casos de uso
        casos = " ".join(norma['metadata_experta']['casos_uso'])

        # Agregar conceptos clave
        conceptos = " ".join(norma['metadata_experta']['conceptos_clave'])

        # Agregar notas
        notas = norma['metadata_experta']['notas_experto']

        # Texto enriquecido
        texto_completo = f"{texto_base}. {casos}. {conceptos}. {notas}"
    else:
        texto_completo = texto_base

    # Generar embedding del texto enriquecido
    return model.encode(texto_completo)
```

EJEMPLO:
```
SIN ENRIQUECIMIENTO:
  Texto: "DECRETO 62 APRUEBA REGLAMENTO DE TRANSFERENCIAS..."
  Embedding: [0.23, -0.45, 0.67, ...]

CON ENRIQUECIMIENTO:
  Texto: "DECRETO 62 APRUEBA REGLAMENTO DE TRANSFERENCIAS...
          Transferencias de suficiencia. Remuneración por disponibilidad.
          suficiencia. potencia firme. valorización.
          Norma principal para potencia. Aplica a generadores >20MW"
  Embedding: [0.28, -0.42, 0.71, ...]  ← MÁS RICO en información

RESULTADO:
  Query: "generador quiere ser remunerado por disponibilidad"

  Sin enriquecimiento: Similitud = 0.65 (puede no aparecer en top 10)
  Con enriquecimiento: Similitud = 0.92 ✅ (aparece #1)
```

VENTAJAS:
✅ Embedding captura conocimiento experto
✅ Mejora precisión dramáticamente
✅ Casos de uso detectados automáticamente


## USO 3: Re-ranking con Reglas Expertas

Después de búsqueda semántica, aplicas reglas del dominio:

```python
def reranking_experto(resultados, caso_caracteristicas):
    """
    caso_caracteristicas = {
        'tipo_empresa': 'generador',
        'tamano_mw': 150,
        'tiene_sscc': True,
        'urgencia': 'alta'
    }
    """

    for norma in resultados:
        score_base = norma['score_semantico']

        # REGLA 1: Si es generador >20MW, prioriza D.62
        if caso_caracteristicas['tipo_empresa'] == 'generador':
            if norma['numero'] == '62' and caso_caracteristicas['tamano_mw'] > 20:
                norma['score_final'] = score_base * 1.5  # Boost 50%

        # REGLA 2: Si tiene SSCC, D.113 es crítico
        if caso_caracteristicas['tiene_sscc']:
            if norma['numero'] == '113':
                norma['score_final'] = score_base * 1.4

        # REGLA 3: Normas de alta frecuencia son más confiables
        frecuencia_norm = norma['metadata_experta']['frecuencia_uso'] / 200
        norma['score_final'] = score_base * (1 + frecuencia_norm * 0.3)

        # REGLA 4: Normas poco usadas penalizan
        if norma['metadata_experta']['vigencia_real'] == 'vigente_poco_usada':
            norma['score_final'] = score_base * 0.8

    return sorted(resultados, key=lambda x: x['score_final'], reverse=True)
```

VENTAJAS:
✅ Incorporas lógica de negocio específica
✅ Reglas transparentes (vs caja negra)
✅ Puedes ajustar según feedback


## USO 4: Anotaciones para Fine-tuning (avanzado)

Si tienes MUCHAS anotaciones expertas (>1,000 casos), puedes fine-tunear:

```python
# Dataset de entrenamiento con anotaciones expertas
casos_anotados = [
    {
        "query": "planta incrementó capacidad instalada",
        "normas_relevantes_experto": ["D.62", "D.113"],  # ← Anotado por experto
        "normas_irrelevantes": ["D.52", "Ley 20571"]
    },
    {
        "query": "disputa con coordinador",
        "normas_relevantes_experto": ["D.52", "Ley 20936"],
        "normas_irrelevantes": ["D.62"]
    },
    # ... 1,000+ casos
]

# Fine-tune modelo embeddings
from sentence_transformers import SentenceTransformer, losses
from torch.utils.data import DataLoader

model = SentenceTransformer('jinaai/jina-embeddings-v2-base-es')

# Preparar training data
train_examples = crear_triplets(casos_anotados)
# Triplets: (query, norma_positiva, norma_negativa)

train_dataloader = DataLoader(train_examples, shuffle=True, batch_size=16)

# Fine-tune
train_loss = losses.TripletLoss(model)
model.fit(
    train_objectives=[(train_dataloader, train_loss)],
    epochs=3,
    warmup_steps=100
)

# Ahora modelo está especializado en normas chilenas
model.save('modelo_normas_chile_finetuned')
```

VENTAJAS:
✅ Modelo aprende patrones del dominio
✅ Mejora precisión +10-15%
✅ Especialización en jerga chilena

DESVENTAJAS:
❌ Requiere >1,000 casos anotados
❌ Requiere GPU para entrenamiento
❌ Mantenimiento complejo


════════════════════════════════════════════════════════════════════════════


## ARQUITECTURA COMPLETA RECOMENDADA

┌──────────────────────────────────────────────────────────────────────────┐
│ 1. FILTRADO (Metadata Experta)                                          │
│    Input:  Query + características del caso                             │
│    Filtros: Tema, relevancia, vigencia_real, frecuencia_uso            │
│    Output: 500 normas candidatas (de 2,031)                             │
│    Tiempo: 5ms                                                           │
├──────────────────────────────────────────────────────────────────────────┤
│ 2. BÚSQUEDA HÍBRIDA (Keywords + Embeddings)                             │
│    a) Keywords en 500 candidatos → Score A                              │
│    b) Embeddings enriquecidos → Score B                                 │
│    c) Fusión: score_final = 0.3*A + 0.7*B                              │
│    Output: Top 50 normas                                                │
│    Tiempo: 60ms                                                          │
├──────────────────────────────────────────────────────────────────────────┤
│ 3. RE-RANKING EXPERTO (Reglas del dominio)                              │
│    Aplica: Boosts por tipo_empresa, tamaño, urgencia                   │
│    Considera: Frecuencia uso, complejidad, vigencia_real               │
│    Output: Top 10 normas finales                                        │
│    Tiempo: 5ms                                                           │
├──────────────────────────────────────────────────────────────────────────┤
│ 4. EXPLICACIÓN (Para transparencia)                                     │
│    Por cada norma en Top 10:                                            │
│    - Score keywords: 0.7                                                │
│    - Score semántico: 0.9                                               │
│    - Boost experto: +0.2 (generador >20MW)                             │
│    - Score final: 0.85                                                  │
│    - Por qué relevante: [casos_uso que matchean]                       │
└──────────────────────────────────────────────────────────────────────────┘

TOTAL: ~70ms, alta precisión, explicable


## ESQUEMA DE DATOS COMPLETO

```python
norma_enriquecida = {
    # Datos base (automáticos)
    "id_norma": "1037065",
    "tipo": "DECRETO",
    "numero": "62",
    "titulo": "APRUEBA REGLAMENTO...",
    "fecha": "2006-06-16",
    "url": "https://...",
    "vinculaciones_ids": ["1002345", "1003456"],
    "temas_detectados": ["POTENCIA", "GENERACION"],

    # Información experta (manual/semi-automática)
    "metadata_experta": {
        # Relevancia por tema (1-10)
        "relevancia_potencia": 10,
        "relevancia_transmision": 3,
        "relevancia_distribucion": 2,

        # Casos de uso (texto libre)
        "casos_uso": [
            "Transferencias de suficiencia",
            "Valorización de potencia",
            "Pagos por disponibilidad"
        ],

        # Conceptos clave (para embeddings)
        "conceptos_clave": [
            "suficiencia",
            "potencia firme",
            "valorización",
            "disponibilidad"
        ],

        # Aplicabilidad
        "aplica_a": {
            "tipo_empresas": ["generador", "transmisor"],
            "tamano_min_mw": 20,
            "requiere_sscc": False
        },

        # Notas del experto
        "notas_experto": "Norma principal para transferencias de potencia. Crítica para generadores >20MW. Actualizada 2023.",

        # Estadísticas de uso real
        "frecuencia_citada": 150,
        "casos_reales_resueltos": 45,
        "vigencia_real": "vigente_critica",  # vs "vigente_poco_usada", "derogada_tacita"

        # Complejidad
        "complejidad": "alta",  # baja, media, alta
        "requiere_experto": True,

        # Relaciones curadas por experto
        "normas_relacionadas_experto": [
            {"id": "1003456", "tipo": "complementa", "importancia": "alta"},
            {"id": "1002345", "tipo": "modifica", "importancia": "media"}
        ],

        # Tags adicionales
        "tags_experto": ["potencia", "valorización", "crítica", "generadores"]
    },

    # Embeddings (generados automáticamente)
    "embeddings": {
        "titulo_base": [0.23, -0.45, ...],  # Solo título
        "enriquecido": [0.28, -0.42, ...]   # Título + metadata_experta
    }
}
```


## FLUJO DE TRABAJO PARA AGREGAR INFORMACIÓN EXPERTA

```
FASE 1: Manual (primeras 50 normas críticas)
  1. Experto identifica 50 normas más importantes
  2. Para cada una, completa template de metadata_experta
  3. Genera embeddings enriquecidos
  4. Testing con casos reales

FASE 2: Semi-automática (siguientes 200 normas)
  1. Sistema sugiere metadata basado en análisis de texto
  2. Experto revisa y corrige
  3. Sistema aprende de correcciones

FASE 3: Crowdsourcing (resto de normas)
  1. Usuarios marcan normas útiles/inútiles
  2. Sistema acumula estadísticas de uso
  3. frecuencia_citada y casos_reales_resueltos se auto-completan
```


════════════════════════════════════════════════════════════════════════════


## RESUMEN: TU ROADMAP ACTUALIZADO

FASE 1 (HOY): Keywords mejorados
  ✅ Expandir sinónimos
  ✅ Fuzzy matching
  ✅ Logging de fallos
  Esfuerzo: 2 horas

FASE 2 (2027): Híbrido básico (si >5K normas)
  ✅ Implementar embeddings (jina-es)
  ✅ Fusión secuencial (keywords → embeddings re-ranking)
  ✅ Empezar metadata_experta en top 50 normas críticas
  Esfuerzo: 2 días (1 día código + 1 día anotar 50 normas)

FASE 3 (2028): Híbrido avanzado + Metadata completa
  ✅ Búsqueda paralela + fusión adaptativa
  ✅ Metadata experta en 300 normas principales
  ✅ Re-ranking con reglas del dominio
  ✅ Embeddings enriquecidos
  Esfuerzo: 1 semana código + 3 días anotaciones

FASE 4 (2030+): Fine-tuning custom (si >100K normas)
  ✅ Modelo fine-tuned específico para normas chilenas
  ✅ Metadata completa crowd-sourced
  ✅ Sistema de feedback continuo
  Esfuerzo: 1 mes


════════════════════════════════════════════════════════════════════════════
CONCLUSIÓN

1. Keywords vs Embeddings: NO eliges, usas AMBOS
   - Secuencial (rápido): keywords filtra → embeddings refina
   - Paralelo (preciso): ambos buscan → fusionas scores
   - Adaptativo (óptimo): decides según tipo de query

2. Información Experta: 4 niveles de uso
   - Metadata para filtrado (fácil, alto impacto)
   - Embeddings enriquecidos (medio esfuerzo, gran mejora)
   - Re-ranking con reglas (transparente, customizable)
   - Fine-tuning (avanzado, requiere >1K anotaciones)

3. Implementación progresiva
   - Empieza simple (keywords)
   - Agrega embeddings cuando crece
   - Incorpora metadata gradualmente (top 50 → top 300 → todas)
   - Fine-tune solo si llega a ser proyecto enterprise
════════════════════════════════════════════════════════════════════════════
