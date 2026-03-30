#!/usr/bin/env python3
"""
Implementación COMPLETA de búsqueda semántica.

USO:
1. pip install sentence-transformers scikit-learn
2. python3 implementar_busqueda_semantica.py --setup  # Primera vez (10 min)
3. python3 implementar_busqueda_semantica.py "tu caso aquí"

NOTA: Requiere 2GB de descarga y ~50MB de cache.
"""

import argparse
import json
import pickle
import time
from pathlib import Path

try:
    from sentence_transformers import SentenceTransformer
    from sklearn.metrics.pairwise import cosine_similarity
    import numpy as np
    DISPONIBLE = True
except ImportError:
    DISPONIBLE = False


def setup_modelo():
    """
    Descarga modelo y calcula embeddings de todas las normas.
    Solo se ejecuta UNA VEZ.
    """
    if not DISPONIBLE:
        print("❌ ERROR: Instala primero: pip install sentence-transformers scikit-learn")
        return False

    print("="*80)
    print("SETUP: Búsqueda Semántica")
    print("="*80)

    # Cargar normas
    print("\n1. Cargando normas...")
    with open('data/busquedas/normas_completas.json') as f:
        data = json.load(f)
    normas = data['normas']
    print(f"   ✓ {len(normas)} normas cargadas")

    # Descargar modelo (2GB, solo primera vez)
    print("\n2. Descargando modelo semántico (2GB, solo primera vez)...")
    print("   Esto puede tomar 5-10 minutos...")
    start = time.time()
    model = SentenceTransformer('paraphrase-multilingual-MiniLM-L12-v2')
    print(f"   ✓ Modelo cargado en {time.time() - start:.1f}s")

    # Calcular embeddings
    print("\n3. Calculando embeddings de normas...")
    print("   Esto puede tomar 5-10 minutos...")
    textos = [n['titulo'] for n in normas]

    start = time.time()
    embeddings = model.encode(textos, show_progress_bar=True, batch_size=32)
    print(f"   ✓ Embeddings calculados en {time.time() - start:.1f}s")

    # Guardar cache
    print("\n4. Guardando cache...")
    cache_dir = Path('data/busquedas/cache_semantica')
    cache_dir.mkdir(exist_ok=True)

    with open(cache_dir / 'embeddings.pkl', 'wb') as f:
        pickle.dump(embeddings, f)

    with open(cache_dir / 'normas_ids.json', 'w') as f:
        json.dump([n['id_norma'] for n in normas], f)

    print(f"   ✓ Cache guardado en {cache_dir}")

    print(f"\n{'='*80}")
    print("✅ SETUP COMPLETO")
    print("="*80)
    print("\nAhora puedes buscar con:")
    print("  python3 implementar_busqueda_semantica.py 'tu caso aquí'")

    return True


def buscar_semantico(caso, top_k=10):
    """
    Búsqueda semántica usando embeddings pre-calculados.
    """
    if not DISPONIBLE:
        print("❌ ERROR: Instala primero: pip install sentence-transformers scikit-learn")
        return

    cache_dir = Path('data/busquedas/cache_semantica')

    # Verificar cache
    if not (cache_dir / 'embeddings.pkl').exists():
        print("❌ ERROR: Ejecuta primero: python3 implementar_busqueda_semantica.py --setup")
        return

    print("="*80)
    print("BÚSQUEDA SEMÁNTICA")
    print("="*80)

    # Cargar modelo
    print("\n1. Cargando modelo...")
    start = time.time()
    model = SentenceTransformer('paraphrase-multilingual-MiniLM-L12-v2')
    print(f"   ✓ Modelo cargado en {time.time() - start:.1f}s")

    # Cargar embeddings y normas
    print("\n2. Cargando cache...")
    with open(cache_dir / 'embeddings.pkl', 'rb') as f:
        embeddings = pickle.load(f)

    with open(cache_dir / 'normas_ids.json') as f:
        normas_ids = json.load(f)

    with open('data/busquedas/normas_completas.json') as f:
        data = json.load(f)
    normas = {n['id_norma']: n for n in data['normas']}

    print(f"   ✓ {len(normas_ids)} embeddings cargados")

    # Calcular embedding del caso
    print(f"\n3. Analizando caso...")
    print(f"   '{caso}'")
    embedding_caso = model.encode([caso])

    # Similitud coseno
    print(f"\n4. Calculando similitudes...")
    start = time.time()
    similitudes = cosine_similarity(embedding_caso, embeddings)[0]
    print(f"   ✓ Similitudes calculadas en {time.time() - start:.3f}s")

    # Ordenar
    indices_ordenados = np.argsort(similitudes)[::-1][:top_k]

    # Mostrar resultados
    print(f"\n{'='*80}")
    print(f"TOP {top_k} NORMAS MÁS RELEVANTES (Búsqueda Semántica)")
    print("="*80)

    resultados = []
    for i, idx in enumerate(indices_ordenados, 1):
        norma_id = normas_ids[idx]
        norma = normas[norma_id]
        similitud = similitudes[idx]

        print(f"\n{i:2}. {norma['tipo']} {norma['numero']:>6} - Similitud: {similitud:.3f}")
        print(f"    {norma['titulo'][:75]}")
        print(f"    Temas: {', '.join(norma.get('temas_detectados', [])[:3])}")
        print(f"    URL: https://www.bcn.cl/leychile/navegar?idNorma={norma_id}")

        resultados.append({
            'id': norma_id,
            'tipo': norma['tipo'],
            'numero': norma['numero'],
            'similitud': float(similitud),
            'titulo': norma['titulo']
        })

    # Guardar resultados
    with open('data/busquedas/ultimo_resultado_semantico.json', 'w', encoding='utf-8') as f:
        json.dump({
            'caso': caso,
            'resultados': resultados
        }, f, indent=2, ensure_ascii=False)

    print(f"\n{'='*80}")
    print("✅ Resultados guardados en: data/busquedas/ultimo_resultado_semantico.json")
    print("="*80)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Búsqueda semántica de normas')
    parser.add_argument('caso', nargs='?', help='Caso a buscar')
    parser.add_argument('--setup', action='store_true', help='Ejecutar setup inicial')
    parser.add_argument('--top', type=int, default=10, help='Número de resultados (default: 10)')

    args = parser.parse_args()

    if args.setup:
        setup_modelo()
    elif args.caso:
        buscar_semantico(args.caso, args.top)
    else:
        print("Uso:")
        print("  python3 implementar_busqueda_semantica.py --setup  # Primera vez")
        print("  python3 implementar_busqueda_semantica.py 'tu caso aquí'")
