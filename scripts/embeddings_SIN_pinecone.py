#!/usr/bin/env python3
"""
DEMOSTRACIÓN: Embeddings SIN Pinecone (100% local, gratis)

Usa solo:
- sentence-transformers (para crear embeddings)
- numpy (para buscar)
- pickle (para guardar)

NO necesita: Pinecone, Chroma, Weaviate, etc.
"""

print("="*80)
print("EMBEDDINGS SIN PINECONE - 100% Local y Gratis")
print("="*80)

print("""
ARQUITECTURA SIMPLE:

┌─────────────────────────────────────────────────┐
│  Paso 1: Crear embeddings (una vez)            │
│  ────────────────────────────────────           │
│  Texto → sentence-transformers → Vector        │
│  "D.62" → [0.23, -0.45, 0.67, ...] (384 dims) │
│                                                 │
│  Paso 2: Guardar en archivo (pickle)          │
│  ────────────────────────────────────          │
│  embeddings = {                                │
│    "250604": [0.23, -0.45, 0.67, ...],        │
│    "258171": [-0.12, 0.89, -0.34, ...],       │
│    ...                                         │
│  }                                             │
│  pickle.dump(embeddings, 'cache.pkl')         │
│                                                │
│  Paso 3: Buscar (numpy)                       │
│  ────────────────────────                     │
│  caso_vector = encode("planta mejoró...")     │
│  similitudes = cosine_similarity(caso_vector, │
│                                  all_vectors)  │
│  top_10 = argsort(similitudes)[:10]           │
└─────────────────────────────────────────────────┘

¿Dónde está Pinecone? NINGÚN LADO - No se necesita!
""")

print("\nCódigo completo (SIN Pinecone):")
print("="*80)

codigo = '''
# ============================================================
# PASO 1: SETUP (una vez) - Crear y guardar embeddings
# ============================================================

from sentence_transformers import SentenceTransformer
import numpy as np
import pickle
import json

# Cargar modelo
model = SentenceTransformer('paraphrase-multilingual-MiniLM-L12-v2')

# Cargar normas
with open('normas_completas.json') as f:
    normas = json.load(f)['normas']

# Crear embeddings
print("Creando embeddings...")
textos = [n['titulo'] for n in normas]
embeddings = model.encode(textos, show_progress_bar=True)

# Guardar en archivo pickle (numpy array)
with open('embeddings.pkl', 'wb') as f:
    pickle.dump({
        'embeddings': embeddings,
        'ids': [n['id_norma'] for n in normas]
    }, f)

print(f"✓ {len(embeddings)} embeddings guardados")
print(f"  Tamaño: {embeddings.nbytes / 1024 / 1024:.1f} MB")

# ============================================================
# PASO 2: BÚSQUEDA (cada vez que consultas)
# ============================================================

# Cargar embeddings desde archivo
with open('embeddings.pkl', 'rb') as f:
    data = pickle.load(f)
    embeddings_normas = data['embeddings']
    ids_normas = data['ids']

# Crear embedding del caso
caso = "planta incrementó su capacidad instalada"
embedding_caso = model.encode([caso])

# Búsqueda con numpy (sin Pinecone!)
from sklearn.metrics.pairwise import cosine_similarity

similitudes = cosine_similarity(embedding_caso, embeddings_normas)[0]
top_10_indices = np.argsort(similitudes)[::-1][:10]

# Resultados
for i, idx in enumerate(top_10_indices, 1):
    norma_id = ids_normas[idx]
    score = similitudes[idx]
    print(f"{i}. Norma {norma_id} - Similitud: {score:.3f}")

# ============================================================
# ESO ES TODO - Sin Pinecone, sin cloud, sin costo
# ============================================================
'''

print(codigo)

print("\n" + "="*80)
print("COMPARACIÓN: Con vs Sin Pinecone")
print("="*80)

print("""
┌─────────────────────────┬───────────────────┬─────────────────────┐
│ Aspecto                 │ Con Numpy (local) │ Con Pinecone        │
├─────────────────────────┼───────────────────┼─────────────────────┤
│ Crear embeddings        │ ✅ Igual          │ ✅ Igual            │
│ Guardar vectores        │ pickle (50MB)     │ Cloud (API)         │
│ Búsqueda 2K vectores    │ 5 ms ⚡           │ 2ms + 30ms red = 32ms│
│ Búsqueda 1M vectores    │ 2000 ms 🐌        │ 50 ms ⚡⚡           │
│ Costo                   │ $0                │ $70/mes             │
│ Setup                   │ 0 min             │ 15 min              │
│ Dependencias            │ numpy, pickle     │ API key, internet   │
│ Funciona offline        │ ✅ Sí             │ ❌ No               │
└─────────────────────────┴───────────────────┴─────────────────────┘

VEREDICTO:
  Con 2,031 vectores: Numpy es MEJOR (más rápido, gratis, local)
  Con 1M+ vectores:   Pinecone es MEJOR (mucho más rápido)

  TÚ TIENES 2K → USA NUMPY
""")

print("\n" + "="*80)
print("¿QUÉ LIBRERÍAS NECESITAS?")
print("="*80)

print("""
OPCIÓN 1: Mínimo absoluto
─────────────────────────
pip install sentence-transformers

Eso es TODO. Incluye:
  ✓ torch (modelo ML)
  ✓ transformers (BERT, etc.)
  ✓ sentence-transformers (wrapper fácil)

Numpy ya lo tienes (viene con Python)
Pickle ya lo tienes (standard library)

OPCIÓN 2: Con scikit-learn (para cosine_similarity más rápido)
───────────────────────────────────────────────────────────────
pip install sentence-transformers scikit-learn

Pero no es necesario, puedes hacer cosine con numpy puro:

def cosine_similarity_numpy(a, b):
    dot = np.dot(a, b.T)
    norm_a = np.linalg.norm(a)
    norm_b = np.linalg.norm(b, axis=1)
    return dot / (norm_a * norm_b)
""")

print("\n" + "="*80)
print("ESTRUCTURA DE ARCHIVOS (todo local)")
print("="*80)

print("""
proyecto/
├── normas_completas.json          (2 MB) - Datos originales
├── embeddings.pkl                 (50 MB) - Vectores guardados
└── buscar.py                      (20 líneas) - Script de búsqueda

ESO ES TODO. No necesitas:
  ❌ Base de datos
  ❌ Servidor
  ❌ Docker
  ❌ Kubernetes
  ❌ Pinecone
  ❌ Cloud
  ❌ API keys
  ❌ Internet (después del setup)
""")

print("\n" + "="*80)
print("EJEMPLO COMPLETO (20 líneas)")
print("="*80)

ejemplo_completo = '''
#!/usr/bin/env python3
from sentence_transformers import SentenceTransformer
import numpy as np
import pickle

# Setup (solo primera vez)
model = SentenceTransformer('paraphrase-multilingual-MiniLM-L12-v2')
# embeddings = model.encode(textos)
# pickle.dump(embeddings, 'cache.pkl')

# Búsqueda (cada vez)
with open('cache.pkl', 'rb') as f:
    embeddings_normas = pickle.load(f)

caso = "planta mejoró capacidad"
embedding_caso = model.encode([caso])

# Cosine similarity con numpy
dot = np.dot(embedding_caso, embeddings_normas.T)
norm_caso = np.linalg.norm(embedding_caso)
norm_normas = np.linalg.norm(embeddings_normas, axis=1)
similitudes = dot / (norm_caso * norm_normas)

# Top 10
top_10 = np.argsort(similitudes[0])[::-1][:10]
print(top_10)

# FIN - ¡Solo 20 líneas!
'''

print(ejemplo_completo)

print("\n" + "="*80)
print("CONCLUSIÓN")
print("="*80)

print("""
RESPUESTA CORTA: NO, no necesitas Pinecone

Embeddings = Crear vectores (sentence-transformers)
Pinecone = Guardar vectores en cloud (opcional)

Para 2,031 vectores:
✅ Usa: numpy + pickle (gratis, local, rápido)
❌ NO uses: Pinecone (overkill, más lento por red, $70/mes)

Pinecone solo si llegas a 100K+ vectores
""")
