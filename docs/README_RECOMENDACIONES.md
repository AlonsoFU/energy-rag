# Guía de Recomendaciones para Búsqueda de Normas BCN

## 📋 Índice de Documentación

### 🎯 Recomendación ACTUAL (Usar esta)
**`recomendacion_CORREGIDA.md`** (19 KB)
- ✅ **Recomendación actualizada y correcta**
- Arquitectura Dual Híbrida: BM25 (2,031 normas) + Embeddings (10 normas críticas)
- Granularidad a nivel de artículos para compliance
- Precisión esperada: 88-92% general, 95% en normas críticas
- Tiempo de implementación: 2 días
- Latencia: ~90ms

### 📚 Documentación de Apoyo

**`RESUMEN_STATE_OF_ART_2025.txt`** (13 KB)
- Resumen ejecutivo de investigación state-of-art 2025
- Benchmarks MTEB, BEIR, MS MARCO
- Comparativa métodos de búsqueda
- RRF vs Weighted Fusion
- Embeddings top 2025

**`state_of_art_2025_retrieval.md`** (22 KB)
- Análisis completo de benchmarks 2025
- Evidencia científica de mejores prácticas
- Arquitectura específica para normas BCN
- Código de ejemplo con RRF

**`arquitectura_hibrida.md`** (26 KB)
- 3 estrategias híbridas (Sequential, Parallel, Adaptive)
- Cómo incorporar información experta (4 niveles)
- Esquema completo de metadata

**`FAQ_HIBRIDO_Y_METADATA.txt`** (17 KB)
- Respuestas directas a preguntas comunes
- Keywords vs embeddings (no es uno u otro, sino ambos)
- Cómo incorporar notas/metadata experta

**`comparativa_escalabilidad.md`** (22 KB)
- Roadmap escalabilidad 2K → 1M normas
- Cuándo migrar tecnologías
- Proyecciones de costos 5 años

**`investigacion_embeddings_2025.md`** (12 KB)
- Investigación sobre paraphrase-multilingual-MiniLM-L12-v2
- Comparativa con mejores alternativas
- Recomendación: jina-embeddings-v2-base-es para español

### ❌ Documentación Obsoleta (NO usar)

**`recomendacion_tu_caso.md`** (19 KB)
- ⚠️ **OBSOLETA** - basada en suposición incorrecta
- Asumía solo títulos sin texto completo
- Recomendaba solo BM25 + metadata
- Usar `recomendacion_CORREGIDA.md` en su lugar

---

## 🎯 Resumen de la Recomendación Actual

### Contexto de Datos
- **2,031 normas** con títulos y metadata en `data/busquedas/normas_completas.json`
- **10 normas críticas** con texto completo en `data/normas_completas/`:
  - Decretos: 62, 13, 44
  - DFL: 4
  - Ley: 19940
  - Resoluciones: 149, 583, 70, 711

### Arquitectura Dual Híbrida

```
┌─────────────────────────────────────────────────────────┐
│  TIER 1: BM25 sobre 2,031 normas (títulos)             │
│  → Top 50 candidatos (50ms)                             │
└─────────────────────────────────────────────────────────┘
                        ↓
┌─────────────────────────────────────────────────────────┐
│  TIER 2: Embeddings sobre 10 normas críticas (artículos)│
│  → Artículos específicos (30ms)                          │
└─────────────────────────────────────────────────────────┘
                        ↓
┌─────────────────────────────────────────────────────────┐
│  TIER 3: RRF Fusion + Metadata Re-ranking               │
│  → Top 10 final (10ms)                                  │
└─────────────────────────────────────────────────────────┘

Total: ~90ms, 88-92% precisión
```

### Ventaja Clave: Granularidad a Nivel de Artículo

**Sin embeddings:**
- "D.62 es relevante para transferencias de potencia" ❌

**Con arquitectura dual:**
- "D.62 Artículo 2º establece específicamente el derecho a vender excedentes" ✅
- "DFL 4 Artículo 150 define las condiciones de conexión" ✅

**Crítico para compliance:** Citar artículos específicos, no solo normas.

### Implementación (2 días)

**Día 1: Preparación de datos (6 horas)**
1. Extraer artículos de las 10 normas con texto completo
2. Generar embeddings (~200-300 artículos, 5 min con GPU)
3. Guardar índice FAISS para búsqueda rápida

**Día 2: Pipeline de búsqueda (8 horas)**
1. Implementar BM25 sobre 2,031 títulos
2. Implementar búsqueda semántica sobre artículos
3. Implementar RRF fusion
4. Agregar metadata re-ranking
5. Testing con casos de compliance reales

### Stack Tecnológico

```python
# Embeddings
jina-embeddings-v2-base-es  # 8192 tokens, MTEB 62.1, 137M params

# Búsqueda
FAISS (local, CPU)          # ~300 artículos = 0.5 MB índice

# Fusion
RRF (k=60)                  # Sin tuning necesario

# Re-ranking
Metadata experta            # relevancia_potencia, frecuencia_uso, vigencia_real
```

### Métricas Esperadas

| Métrica | Valor |
|---------|-------|
| Precisión general | 88-92% |
| Precisión normas críticas | 95% |
| Latencia | 90ms |
| Recall@10 | 85% |
| Costo | $0 (local) |

### Escalabilidad Futura

**Cuando crezca a >5K normas con texto completo:**
- Migrar a 3-way retrieval (BM25 + Dense + Sparse)
- Agregar ColBERT reranking
- Precisión objetivo: 92-95%
- Latencia: <150ms

---

## 📝 Estado de Implementación

### ✅ Completado
- [x] Investigación state-of-art 2025
- [x] Análisis de datos disponibles
- [x] Diseño de arquitectura dual
- [x] Código de ejemplo con RRF
- [x] Documentación completa

### 🔄 Pendiente (siguiente paso)
- [ ] Verificar que las 10 normas con texto completo son las más críticas
- [ ] Implementar extracción de artículos
- [ ] Generar embeddings
- [ ] Implementar pipeline de búsqueda dual
- [ ] Testing con casos de compliance

---

## 🚀 Cómo Empezar

1. **Leer recomendación completa:**
   ```bash
   cat docs/recomendacion_CORREGIDA.md
   ```

2. **Revisar código de ejemplo:**
   ```bash
   cat scripts/arquitectura_actualizada_2025.py
   ```

3. **Verificar normas con texto completo:**
   ```bash
   ls -lh data/normas_completas/*/*.json
   ```

4. **Implementar según plan en `recomendacion_CORREGIDA.md`**

---

## 📊 Comparativa Rápida

| Aspecto | Recomendación Obsoleta | Recomendación ACTUAL |
|---------|------------------------|----------------------|
| Datos | Solo títulos ❌ | Títulos + 10 textos completos ✅ |
| Método | BM25 + metadata | BM25 + Embeddings + RRF |
| Granularidad | Norma completa | Artículos específicos ✅ |
| Precisión | 70% → 85% | 88-92% (95% críticas) ✅ |
| Compliance | "D.62 relevante" | "D.62 Art. 2º específico" ✅ |
| Tiempo | 6 horas | 2 días |
| Escalable | No | Sí ✅ |

---

## 🔗 Referencias

- MTEB Leaderboard (Hugging Face)
- Azure AI Search hybrid retrieval (Microsoft)
- IBM 3-way retrieval research (2025)
- NVIDIA chunking benchmarks
- Elasticsearch Labs (RRF)
- Stanford ColBERT

---

**Última actualización:** 2025-01-24
**Versión:** 2.0 (Corrección post-análisis de datos)
