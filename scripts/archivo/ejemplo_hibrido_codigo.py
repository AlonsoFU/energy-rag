#!/usr/bin/env python3
"""
EJEMPLO PRÁCTICO: Búsqueda Híbrida (Keywords + Embeddings + Metadata Experta)

Muestra 3 estrategias:
1. Secuencial (keywords → embeddings re-ranking)
2. Paralela (fusión de scores)
3. Adaptativa (elige según tipo de query)
"""

import json
import re
import numpy as np
from typing import List, Dict, Tuple


# ============================================================================
# SIMULACIÓN (sin sentence-transformers instalado)
# ============================================================================

class ModeloEmbeddingSimulado:
    """Simula modelo de embeddings para ejemplo"""
    def encode(self, textos):
        # Simula embeddings (en real usarías sentence-transformers)
        if isinstance(textos, str):
            textos = [textos]
        return np.random.rand(len(textos), 384)


# ============================================================================
# ESTRATEGIA 1: SECUENCIAL (Filtro + Re-ranking)
# ============================================================================

def busqueda_secuencial(query: str, normas: List[Dict], embeddings: np.ndarray,
                       model, top_k=10) -> List[Dict]:
    """
    PASO 1: Keywords filtra a 200 candidatos (rápido)
    PASO 2: Embeddings re-rankea candidatos (preciso)

    Ventaja: Rápido (keywords reduce espacio de búsqueda)
    """
    print("\n" + "="*80)
    print("ESTRATEGIA 1: SECUENCIAL (Keywords → Embeddings)")
    print("="*80)

    # PASO 1: Filtrado con keywords
    print(f"\nPASO 1: Filtrado con keywords")
    print(f"  Query: '{query}'")

    keywords_query = extraer_keywords(query)
    print(f"  Keywords: {keywords_query}")

    candidatos_indices = []
    candidatos_scores_kw = []

    for i, norma in enumerate(normas):
        score_kw = calcular_score_keywords(keywords_query, norma)
        if score_kw > 0.1:  # Umbral mínimo
            candidatos_indices.append(i)
            candidatos_scores_kw.append(score_kw)

    print(f"  ✓ Filtrados: {len(candidatos_indices)} de {len(normas)} normas")

    if len(candidatos_indices) == 0:
        print("  ⚠️  Sin candidatos, retornando búsqueda semántica completa")
        return busqueda_solo_embeddings(query, normas, embeddings, model, top_k)

    # PASO 2: Re-ranking semántico de candidatos
    print(f"\nPASO 2: Re-ranking semántico de {len(candidatos_indices)} candidatos")

    query_emb = model.encode(query)
    candidatos_embs = embeddings[candidatos_indices]

    # Similitud coseno
    scores_semanticos = cosine_similarity(query_emb.reshape(1, -1), candidatos_embs)[0]

    # Combinar resultados
    resultados = []
    for idx, score_sem in zip(candidatos_indices, scores_semanticos):
        resultados.append({
            'norma': normas[idx],
            'score_semantico': float(score_sem),
            'score_keywords': candidatos_scores_kw[candidatos_indices.index(idx)],
            'indice': idx
        })

    # Ordenar por score semántico
    resultados.sort(key=lambda x: x['score_semantico'], reverse=True)

    print(f"  ✓ Top 10 por similitud semántica:")
    for i, r in enumerate(resultados[:top_k], 1):
        print(f"    {i}. {r['norma']['numero']:6s} - Semántico: {r['score_semantico']:.3f}, Keywords: {r['score_keywords']:.3f}")

    return resultados[:top_k]


# ============================================================================
# ESTRATEGIA 2: PARALELA (Fusión de Scores)
# ============================================================================

def busqueda_paralela(query: str, normas: List[Dict], embeddings: np.ndarray,
                     model, top_k=10, alpha=0.3) -> List[Dict]:
    """
    Ejecuta AMBAS búsquedas en paralelo y fusiona scores

    score_final = alpha * score_keywords + (1-alpha) * score_embeddings

    alpha = 0.3 → Favorece embeddings (70%)
    alpha = 0.5 → Balance 50/50
    alpha = 0.7 → Favorece keywords (70%)

    Ventaja: No pierdes buenos resultados de ningún método
    """
    print("\n" + "="*80)
    print(f"ESTRATEGIA 2: PARALELA (Fusión α={alpha})")
    print("="*80)

    # BÚSQUEDA 1: Keywords
    print(f"\nBÚSQUEDA A: Keywords")
    keywords_query = extraer_keywords(query)
    scores_keywords = np.zeros(len(normas))

    for i, norma in enumerate(normas):
        scores_keywords[i] = calcular_score_keywords(keywords_query, norma)

    print(f"  Top 3: {np.argsort(scores_keywords)[::-1][:3]}")

    # BÚSQUEDA 2: Embeddings
    print(f"\nBÚSQUEDA B: Embeddings")
    query_emb = model.encode(query)
    scores_embeddings = cosine_similarity(query_emb.reshape(1, -1), embeddings)[0]

    print(f"  Top 3: {np.argsort(scores_embeddings)[::-1][:3]}")

    # FUSIÓN
    print(f"\nFUSIÓN: score_final = {alpha}*keywords + {1-alpha}*embeddings")

    # Normalizar scores a [0, 1]
    scores_kw_norm = normalizar(scores_keywords)
    scores_emb_norm = normalizar(scores_embeddings)

    # Fusión lineal
    scores_finales = alpha * scores_kw_norm + (1 - alpha) * scores_emb_norm

    # Top K
    top_indices = np.argsort(scores_finales)[::-1][:top_k]

    resultados = []
    for idx in top_indices:
        resultados.append({
            'norma': normas[idx],
            'score_keywords': float(scores_keywords[idx]),
            'score_embeddings': float(scores_embeddings[idx]),
            'score_final': float(scores_finales[idx]),
            'indice': idx
        })

    print(f"\n  ✓ Top 10 fusionados:")
    for i, r in enumerate(resultados, 1):
        print(f"    {i}. {r['norma']['numero']:6s} - Final: {r['score_final']:.3f} "
              f"(KW: {r['score_keywords']:.3f}, Emb: {r['score_embeddings']:.3f})")

    return resultados


# ============================================================================
# ESTRATEGIA 3: ADAPTATIVA (Decide según tipo de query)
# ============================================================================

def busqueda_adaptativa(query: str, normas: List[Dict], embeddings: np.ndarray,
                       model, top_k=10) -> List[Dict]:
    """
    Analiza el query y decide qué estrategia usar:

    - Query con número de decreto → Solo keywords (rápido, exacto)
    - Query natural/sinónimos → Solo embeddings (entiende contexto)
    - Query mixta → Híbrido (fusión)

    Ventaja: Usa el método más apropiado para cada caso
    """
    print("\n" + "="*80)
    print("ESTRATEGIA 3: ADAPTATIVA (Decide según query)")
    print("="*80)

    # Analizar características del query
    tiene_num_decreto = bool(re.search(r'(decreto|ley|resolución|d\.)\s*\d+', query.lower()))
    keywords_tecnicas = extraer_keywords_tecnicas(query)
    tiene_keywords_exactas = len(keywords_tecnicas) > 2

    print(f"\nAnálisis del query: '{query}'")
    print(f"  ¿Tiene número decreto?: {tiene_num_decreto}")
    print(f"  Keywords técnicas: {keywords_tecnicas}")
    print(f"  ¿Terminología técnica?: {tiene_keywords_exactas}")

    # Decisión
    if tiene_num_decreto:
        print(f"\n  → DECISIÓN: Usar KEYWORDS (query específica)")
        return busqueda_solo_keywords(query, normas, top_k)

    elif not tiene_keywords_exactas:
        print(f"\n  → DECISIÓN: Usar EMBEDDINGS (lenguaje natural)")
        return busqueda_solo_embeddings(query, normas, embeddings, model, top_k)

    else:
        print(f"\n  → DECISIÓN: Usar HÍBRIDO (query mixta)")
        return busqueda_paralela(query, normas, embeddings, model, top_k, alpha=0.3)


# ============================================================================
# INCORPORAR METADATA EXPERTA
# ============================================================================

def busqueda_con_metadata_experta(query: str, normas: List[Dict],
                                 embeddings: np.ndarray, model,
                                 caso_caracteristicas: Dict = None,
                                 top_k=10) -> List[Dict]:
    """
    Usa información experta para mejorar resultados:

    1. Filtrado por metadata (relevancia, vigencia)
    2. Búsqueda híbrida en candidatos
    3. Re-ranking con reglas expertas
    4. Boost por frecuencia de uso
    """
    print("\n" + "="*80)
    print("BÚSQUEDA CON METADATA EXPERTA")
    print("="*80)

    caso_caracteristicas = caso_caracteristicas or {}

    # PASO 1: Filtrado por metadata
    print(f"\nPASO 1: Filtrado por metadata experta")

    candidatos = []
    candidatos_indices = []

    for i, norma in enumerate(normas):
        if 'metadata_experta' not in norma:
            continue

        metadata = norma['metadata_experta']

        # Filtros
        if metadata.get('vigencia_real') == 'vigente_critica':
            relevancia_ok = True
        elif metadata.get('frecuencia_uso', 0) >= 50:
            relevancia_ok = True
        else:
            relevancia_ok = False

        if relevancia_ok:
            candidatos.append(norma)
            candidatos_indices.append(i)

    print(f"  ✓ Filtrados: {len(candidatos)} normas críticas de {len(normas)}")

    if len(candidatos) == 0:
        print("  ⚠️  Sin candidatos con metadata, usando todas las normas")
        candidatos = normas
        candidatos_indices = list(range(len(normas)))

    # PASO 2: Búsqueda híbrida en candidatos
    print(f"\nPASO 2: Búsqueda híbrida en candidatos")

    candidatos_embeddings = embeddings[candidatos_indices]
    resultados = busqueda_paralela(query, candidatos, candidatos_embeddings,
                                  model, top_k=50, alpha=0.3)

    # PASO 3: Re-ranking con reglas expertas
    print(f"\nPASO 3: Re-ranking con reglas del dominio")

    for r in resultados:
        norma = r['norma']
        score_base = r['score_final']

        # Inicializar score final
        score_final = score_base
        explicacion = []

        # REGLA 1: Boost por tipo de empresa
        if 'metadata_experta' in norma:
            metadata = norma['metadata_experta']

            # Si es generador y norma aplica a generadores
            if caso_caracteristicas.get('tipo_empresa') == 'generador':
                if 'generador' in metadata.get('aplica_a', {}).get('tipo_empresas', []):
                    score_final *= 1.3
                    explicacion.append("Aplica a generadores (+30%)")

            # Boost por frecuencia de uso
            frecuencia = metadata.get('frecuencia_uso', 0)
            if frecuencia > 100:
                boost_freq = min(frecuencia / 500, 0.2)
                score_final += boost_freq
                explicacion.append(f"Alta frecuencia uso ({frecuencia} citas, +{boost_freq:.2f})")

            # Penalizar normas poco usadas
            if metadata.get('vigencia_real') == 'vigente_poco_usada':
                score_final *= 0.7
                explicacion.append("Poco usada en práctica (-30%)")

        r['score_final_experto'] = score_final
        r['explicacion'] = "; ".join(explicacion)

    # Reordenar por score final experto
    resultados.sort(key=lambda x: x.get('score_final_experto', 0), reverse=True)

    print(f"\n  ✓ Top 10 con re-ranking experto:")
    for i, r in enumerate(resultados[:top_k], 1):
        print(f"    {i}. {r['norma']['numero']:6s} - "
              f"Score: {r.get('score_final_experto', 0):.3f} "
              f"(base: {r['score_final']:.3f})")
        if r.get('explicacion'):
            print(f"       → {r['explicacion']}")

    return resultados[:top_k]


# ============================================================================
# FUNCIONES AUXILIARES
# ============================================================================

def extraer_keywords(texto: str) -> List[str]:
    """Extrae keywords simples del texto"""
    # Limpiar y tokenizar
    texto = texto.lower()
    palabras = re.findall(r'\b\w+\b', texto)

    # Remover stopwords
    stopwords = {'de', 'la', 'el', 'en', 'a', 'los', 'las', 'del', 'y', 'o', 'su'}
    keywords = [p for p in palabras if p not in stopwords and len(p) > 3]

    return keywords


def extraer_keywords_tecnicas(texto: str) -> List[str]:
    """Extrae keywords técnicas del sector eléctrico"""
    texto_lower = texto.lower()

    keywords_tecnicas = []
    terminos_tecnicos = [
        'potencia', 'suficiencia', 'transferencias', 'coordinador',
        'generador', 'transmisor', 'distribuidor', 'sscc', 'central',
        'decreto', 'ley', 'resolución', 'reglamento'
    ]

    for termino in terminos_tecnicos:
        if termino in texto_lower:
            keywords_tecnicas.append(termino)

    return keywords_tecnicas


def calcular_score_keywords(keywords_query: List[str], norma: Dict) -> float:
    """Calcula score de similitud por keywords"""
    titulo = norma.get('titulo', '').lower()
    temas = [t.lower() for t in norma.get('temas_detectados', [])]

    score = 0
    for kw in keywords_query:
        if kw in titulo:
            score += 1.0
        if kw in ' '.join(temas):
            score += 0.5

    # Normalizar por número de keywords
    if len(keywords_query) > 0:
        score = score / len(keywords_query)

    return score


def cosine_similarity(a, b):
    """Similitud coseno"""
    dot_product = np.dot(a, b.T)
    norm_a = np.linalg.norm(a, axis=1, keepdims=True)
    norm_b = np.linalg.norm(b, axis=1, keepdims=True)
    return dot_product / (norm_a * norm_b.T)


def normalizar(scores):
    """Normaliza scores a [0, 1]"""
    min_score = scores.min()
    max_score = scores.max()

    if max_score == min_score:
        return np.zeros_like(scores)

    return (scores - min_score) / (max_score - min_score)


def busqueda_solo_keywords(query: str, normas: List[Dict], top_k=10) -> List[Dict]:
    """Búsqueda solo con keywords"""
    keywords_query = extraer_keywords(query)

    resultados = []
    for i, norma in enumerate(normas):
        score = calcular_score_keywords(keywords_query, norma)
        if score > 0:
            resultados.append({
                'norma': norma,
                'score_keywords': score,
                'indice': i
            })

    resultados.sort(key=lambda x: x['score_keywords'], reverse=True)
    return resultados[:top_k]


def busqueda_solo_embeddings(query: str, normas: List[Dict], embeddings: np.ndarray,
                            model, top_k=10) -> List[Dict]:
    """Búsqueda solo con embeddings"""
    query_emb = model.encode(query)
    scores = cosine_similarity(query_emb.reshape(1, -1), embeddings)[0]

    top_indices = np.argsort(scores)[::-1][:top_k]

    resultados = []
    for idx in top_indices:
        resultados.append({
            'norma': normas[idx],
            'score_embeddings': float(scores[idx]),
            'indice': idx
        })

    return resultados


# ============================================================================
# EJEMPLO DE USO
# ============================================================================

if __name__ == "__main__":
    # Cargar normas
    with open('data/busquedas/normas_completas.json', 'r', encoding='utf-8') as f:
        data = json.load(f)
        normas = data['normas']

    print(f"Cargadas {len(normas)} normas")

    # Agregar metadata experta de ejemplo a algunas normas
    for norma in normas:
        if norma['numero'] == '62':
            norma['metadata_experta'] = {
                'relevancia_potencia': 10,
                'casos_uso': [
                    'Transferencias de suficiencia',
                    'Valorización de potencia'
                ],
                'conceptos_clave': ['suficiencia', 'potencia firme', 'valorización'],
                'frecuencia_uso': 150,
                'vigencia_real': 'vigente_critica',
                'aplica_a': {
                    'tipo_empresas': ['generador', 'transmisor'],
                    'tamano_min_mw': 20
                }
            }

    # Simular embeddings (en real, usarías sentence-transformers)
    print("\nGenerando embeddings simulados...")
    model = ModeloEmbeddingSimulado()
    titulos = [n['titulo'] for n in normas]
    embeddings = model.encode(titulos)
    print(f"✓ Generados {len(embeddings)} embeddings de dimensión {embeddings.shape[1]}")

    # DEMO: Diferentes queries
    queries_demo = [
        "decreto 62",  # Query específica → keywords
        "planta incrementó capacidad instalada",  # Natural → embeddings
        "decreto sobre suficiencia",  # Mixta → híbrido
    ]

    for query in queries_demo:
        print("\n" + "="*80)
        print(f"DEMO: Query = '{query}'")
        print("="*80)

        # Estrategia adaptativa
        resultados = busqueda_adaptativa(query, normas, embeddings, model, top_k=5)

        input("\nPresiona Enter para continuar...")

    # DEMO: Con metadata experta
    print("\n" + "="*80)
    print("DEMO: Búsqueda con metadata experta")
    print("="*80)

    query = "transferencias de potencia para generador"
    caso = {
        'tipo_empresa': 'generador',
        'tamano_mw': 150,
        'tiene_sscc': True
    }

    resultados = busqueda_con_metadata_experta(
        query, normas, embeddings, model,
        caso_caracteristicas=caso,
        top_k=5
    )

    print("\n✓ Demo completado")
