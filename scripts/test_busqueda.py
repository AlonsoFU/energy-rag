#!/usr/bin/env python3
"""
Script de test para el sistema de búsqueda semántica de normas BCN.

Ejecuta una serie de queries de prueba y muestra métricas de rendimiento.
"""

import sys
import time
from pathlib import Path

# Agregar src al path
sys.path.insert(0, str(Path(__file__).parent.parent / 'src'))

from search.hybrid_search import HybridSearch, format_result


# Queries de prueba para el dominio eléctrico chileno
TEST_QUERIES = [
    # Términos técnicos específicos
    "transferencias de potencia",
    "servicios complementarios frecuencia",
    "balance de inyecciones y retiros",

    # Conceptos generales (test semántico)
    "pago por uso de líneas de transmisión",
    "obligaciones del coordinador eléctrico",
    "penalidades por incumplimiento",

    # Preguntas de compliance
    "plazos para declarar costos",
    "requisitos técnicos generación",
]


def test_search_performance(engine: HybridSearch):
    """Mide latencia de búsqueda."""
    query = "transferencias de potencia"

    # Warmup
    engine.search(query, top_k=5)

    # Medir
    times = []
    for _ in range(5):
        start = time.perf_counter()
        engine.search(query, top_k=10)
        times.append(time.perf_counter() - start)

    avg_time = sum(times) / len(times) * 1000
    print(f"\nLatencia promedio: {avg_time:.1f}ms")
    return avg_time


def compare_search_modes(engine: HybridSearch, query: str):
    """Compara resultados de BM25, semántico e híbrido."""
    print(f"\n{'='*60}")
    print(f"Query: '{query}'")
    print('='*60)

    # BM25
    print("\n[BM25]")
    bm25_results = engine.search_bm25_only(query, top_k=3)
    for i, r in enumerate(bm25_results, 1):
        print(f"  {i}. [{r.tipo_norma} {r.numero_norma}] Art. {r.numero_articulo}")

    # Semántico
    print("\n[Semántico]")
    sem_results = engine.search_semantic_only(query, top_k=3)
    for i, r in enumerate(sem_results, 1):
        print(f"  {i}. [{r.tipo_norma} {r.numero_norma}] Art. {r.numero_articulo}")

    # Híbrido
    print("\n[Híbrido (RRF)]")
    hybrid_results = engine.search(query, top_k=3)
    for i, r in enumerate(hybrid_results, 1):
        print(f"  {i}. [{r.tipo_norma} {r.numero_norma}] Art. {r.numero_articulo} (BM25:#{r.bm25_rank}, Sem:#{r.semantic_rank})")


def run_all_tests(engine: HybridSearch):
    """Ejecuta todas las queries de prueba."""
    print("\n" + "="*60)
    print("TEST DE BÚSQUEDA HÍBRIDA - NORMAS BCN")
    print("="*60)

    for query in TEST_QUERIES:
        print(f"\n>>> {query}")
        results = engine.search(query, top_k=3)

        if not results:
            print("  (sin resultados)")
            continue

        for i, r in enumerate(results, 1):
            text_preview = r.texto[:100].replace('\n', ' ')
            print(f"  {i}. [{r.tipo_norma} {r.numero_norma}] Art. {r.numero_articulo}")
            print(f"     {text_preview}...")


def main():
    import argparse

    parser = argparse.ArgumentParser(description='Test de búsqueda semántica BCN')
    parser.add_argument(
        '--index-dir',
        type=Path,
        default=Path(__file__).parent.parent / 'data' / 'search_index',
        help='Directorio con índice FAISS'
    )
    parser.add_argument(
        '--query',
        type=str,
        help='Query específica a probar'
    )
    parser.add_argument(
        '--compare',
        action='store_true',
        help='Comparar modos de búsqueda'
    )
    parser.add_argument(
        '--benchmark',
        action='store_true',
        help='Medir latencia'
    )

    args = parser.parse_args()

    print("Inicializando motor de búsqueda...")
    engine = HybridSearch(args.index_dir)

    if args.benchmark:
        test_search_performance(engine)
        return

    if args.query:
        if args.compare:
            compare_search_modes(engine, args.query)
        else:
            results = engine.search(args.query, top_k=5)
            print(f"\n--- Resultados para: '{args.query}' ---\n")
            for i, r in enumerate(results, 1):
                print(f"{i}. {format_result(r)}\n")
        return

    # Tests por defecto
    run_all_tests(engine)

    # Comparar modos para query específica
    compare_search_modes(engine, "transferencias de potencia")

    # Benchmark
    test_search_performance(engine)

    print("\n✓ Tests completados")


if __name__ == '__main__':
    main()
