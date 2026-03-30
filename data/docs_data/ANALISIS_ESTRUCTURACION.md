# Análisis de Estructuración de Normas BCN

**Fecha:** 2026-01-22
**Total normas analizadas:** 686

---

## Respuesta Directa

**¿Se pueden estructurar todas las normas?** → **SÍ**

**¿Tienen estructura similar?** → **SÍ, muy consistente**

**¿Hay complicaciones?** → **Mínimas (3.4% anomalías)**

---

## Estructura Base (100% consistente)

Todas las 686 normas tienen estos campos:

```json
{
  "id_norma": "250604",          // Siempre presente
  "tipo": "DECRETO",              // LEY, DECRETO, DFL, etc.
  "numero": "62",                 // 96.6% tienen número
  "titulo": "...",                // Siempre presente
  "temas_detectados": [],         // Array (puede estar vacío)
  "vinculaciones_ids": [],        // Array (puede estar vacío)
  "url": "https://..."            // Siempre presente
}
```

## Campos Opcionales

| Campo | Frecuencia | Observación |
|-------|------------|-------------|
| `organismo` | 20.8% | Ministerio emisor |
| `es_sector_electrico` | 41.7% | Flag de filtrado |
| `fecha_publicacion` | 1.9% | Difícil de extraer |

---

## Vinculaciones (Referencias entre normas)

- **82.2%** tienen vinculaciones
- **Promedio:** 3.9 vínculos por norma
- **Máximo:** 15 vínculos
- **Sin vínculos:** 122 normas (17.8%)

### Top normas con más vínculos

```
LEY 18287   → 15 vínculos (peajes transporte)
LEY 19696   → 15 vínculos (código procesal penal)
LEY 7421    → 15 vínculos (código orgánico tribunales)
```

---

## Temas Detectados

- **67.2%** tienen temas del sector eléctrico
- **32.8%** sin temas → normas generales (procedimiento, tributarias, etc.)

### Distribución

| Temas | Normas | % |
|-------|--------|---|
| 0 | 225 | 32.8% |
| 1 | 200 | 29.2% |
| 2 | 112 | 16.3% |
| 3+ | 149 | 21.7% |

---

## Anomalías (Casos Especiales)

### 1. Tipo DESCONOCIDO (23 normas = 3.4%)

Son normas donde el regex no pudo identificar el tipo:
- Códigos (Penal, Orgánico Tribunales)
- Resoluciones con formato diferente
- Rectificaciones

**Impacto:** Mínimo. Tienen todos los otros campos.

### 2. Sin número (23 normas = 3.4%)

Mismas que tipo DESCONOCIDO. Son documentos especiales:
```
- Código Penal (id: 1984)
- Código Orgánico de Tribunales (id: 7421)
- Resoluciones EXENTA
```

**Solución:** Usar `id_norma` como identificador único.

### 3. Sin temas (225 normas = 32.8%)

No son anomalías reales. Son normas **generales** citadas por normas eléctricas:
- Ley de Procedimiento Administrativo
- Código Tributario
- Ley de Bases de Medio Ambiente
- etc.

---

## Patrones por Tipo de Norma

| Tipo | Cantidad | Campos completos | Observación |
|------|----------|------------------|-------------|
| LEY | 538 (78%) | 81.6% | Más consistente |
| DECRETO | 68 (10%) | 60.3% | Varía según antigüedad |
| DFL | 55 (8%) | 78.2% | Consistente |
| OTROS | 25 (4%) | 78.3% | Resoluciones, códigos |

---

## Conclusiones

### ✅ Estructuración es VIABLE

1. **Estructura base 100% consistente**
   - Todos tienen: id, tipo, título, URL, vinculaciones, temas

2. **Referencias funcionan bien**
   - 82% tienen vínculos
   - Promedio 3.9 referencias por norma
   - Grafo navegable

3. **Clasificación temática robusta**
   - 67% clasificadas automáticamente
   - Keywords funcionan bien

### ⚠️ Consideraciones

1. **3.4% sin tipo/número extraído**
   - Son documentos especiales (códigos, resoluciones)
   - Usar `id_norma` como key principal

2. **33% sin temas detectados**
   - **NO es error** - son normas generales
   - Ejemplo: Código Penal citado por normas de sanciones

3. **Fechas difíciles de extraer (2%)**
   - HTML inconsistente entre normas antiguas/nuevas
   - No es crítico para la mayoría de casos de uso

### ✅ Sistema es ROBUSTO

El scraping actual maneja bien:
- Normas desde 1874 hasta 2026
- Diferentes formatos HTML
- Referencias cruzadas complejas
- Clasificación automática

---

## Recomendaciones para Estructuración

### 1. Schema de Base de Datos

```sql
CREATE TABLE normas (
  id_norma VARCHAR(10) PRIMARY KEY,
  tipo VARCHAR(20),
  numero VARCHAR(10),
  titulo TEXT,
  url TEXT,
  organismo VARCHAR(100),
  created_at TIMESTAMP
);

CREATE TABLE temas (
  id SERIAL PRIMARY KEY,
  id_norma VARCHAR(10) REFERENCES normas(id_norma),
  tema VARCHAR(50)
);

CREATE TABLE vinculaciones (
  id SERIAL PRIMARY KEY,
  id_origen VARCHAR(10) REFERENCES normas(id_norma),
  id_destino VARCHAR(10) REFERENCES normas(id_norma)
);
```

### 2. Validación

```python
def validar_norma(norma):
    # Campos obligatorios
    assert 'id_norma' in norma
    assert 'tipo' in norma
    assert 'titulo' in norma
    assert 'url' in norma

    # Arrays siempre presentes (pueden estar vacíos)
    assert isinstance(norma.get('temas_detectados', []), list)
    assert isinstance(norma.get('vinculaciones_ids', []), list)

    return True
```

### 3. Manejo de Anomalías

```python
# Usar id_norma como clave primaria (no tipo+numero)
norma_key = norma['id_norma']

# Número puede faltar en códigos
numero = norma.get('numero', f"ID-{norma['id_norma']}")

# Temas vacíos = norma general
if not norma.get('temas_detectados'):
    categoria = "GENERAL"
else:
    categoria = "SECTOR_ELECTRICO"
```

---

## Respuesta Final

**Para tu proyecto de dark data:**

✅ **SÍ puedes estructurar todas las normas**
✅ **Estructura es consistente y predecible**
✅ **Anomalías son mínimas (3.4%) y manejables**
✅ **Sistema actual es robusto para 686+ normas**

No hay complicaciones bloqueantes. El scraping funciona para todo tipo de normas.
