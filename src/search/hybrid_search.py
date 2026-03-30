"""
Pipeline de búsqueda híbrida para normas legales chilenas.

Combina:
1. BM25 (búsqueda léxica) para términos exactos
2. Embeddings (búsqueda semántica) para significado
3. RRF (Reciprocal Rank Fusion) para combinar resultados
4. Cross-Encoder (reranking) para precisión final
"""

import json
import pickle
import re
from pathlib import Path
from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass
import numpy as np

try:
    from sentence_transformers import SentenceTransformer
    from rank_bm25 import BM25Okapi
    import faiss
except ImportError:
    print("Instalando dependencias...")
    import subprocess
    subprocess.run(["pip", "install", "sentence-transformers", "faiss-cpu", "rank-bm25", "-q"])
    from sentence_transformers import SentenceTransformer
    from rank_bm25 import BM25Okapi
    import faiss


@dataclass
class SearchResult:
    """Resultado de búsqueda individual."""
    article_id: str
    id_norma: str
    tipo_norma: str
    numero_norma: str
    titulo_norma: str
    numero_articulo: str
    texto: str
    score: float
    # Scores individuales para debugging
    bm25_rank: Optional[int] = None
    semantic_rank: Optional[int] = None
    rerank_score: Optional[float] = None  # Score del Cross-Encoder


class HybridSearch:
    """
    Motor de búsqueda híbrida combinando BM25 + Embeddings + RRF.
    """

    def __init__(
        self,
        index_dir: Path,
        model_name: str = "intfloat/multilingual-e5-base",
        rrf_k: int = 60
    ):
        """
        Args:
            index_dir: Directorio con índice FAISS y metadata
            model_name: Modelo para embeddings de queries
            rrf_k: Parámetro k de RRF (default 60 según literatura)
        """
        self.index_dir = Path(index_dir)
        self.rrf_k = rrf_k
        self.model_name = model_name

        # Cargar índice FAISS y metadata
        print("Cargando índice FAISS...")
        self.faiss_index = faiss.read_index(str(self.index_dir / "articles.faiss"))

        with open(self.index_dir / "articles_metadata.pkl", 'rb') as f:
            self.articles = pickle.load(f)

        print(f"  - {len(self.articles)} artículos cargados")

        # Cargar modelo para queries
        print(f"Cargando modelo: {model_name}")
        self.model = SentenceTransformer(model_name)

        # Crear índice BM25
        print("Creando índice BM25...")
        self._build_bm25_index()

        print("✓ Motor de búsqueda listo")

    def _build_bm25_index(self):
        """Construye índice BM25 sobre los textos de artículos."""
        # Tokenizar textos (simple: lowercase + split)
        self.tokenized_corpus = [
            self._tokenize(a['texto']) for a in self.articles
        ]
        self.bm25 = BM25Okapi(self.tokenized_corpus)

    def _tokenize(self, text: str) -> List[str]:
        """Tokenización simple para BM25."""
        # Lowercase y remover puntuación
        text = text.lower()
        text = re.sub(r'[^\w\sáéíóúñü]', ' ', text)
        tokens = text.split()
        # Remover stopwords básicas
        stopwords = {'el', 'la', 'los', 'las', 'de', 'del', 'en', 'a', 'y', 'o', 'que', 'un', 'una', 'por', 'para', 'con', 'se', 'su', 'al', 'es'}
        return [t for t in tokens if t not in stopwords and len(t) > 2]

    def _encode_query(self, query: str) -> np.ndarray:
        """Genera embedding para query."""
        # e5 models usan prefijo "query: " para queries
        if 'e5' in self.model_name.lower():
            query = f"query: {query}"

        embedding = self.model.encode(
            query,
            normalize_embeddings=True,
            convert_to_numpy=True
        )
        return embedding.reshape(1, -1)

    def search_bm25(self, query: str, top_k: int = 50) -> List[Tuple[int, float]]:
        """
        Búsqueda BM25 (léxica).

        Returns:
            Lista de (índice, score) ordenados por relevancia
        """
        query_tokens = self._tokenize(query)
        scores = self.bm25.get_scores(query_tokens)

        # Obtener top_k índices ordenados por score
        top_indices = np.argsort(scores)[::-1][:top_k]

        return [(int(idx), float(scores[idx])) for idx in top_indices if scores[idx] > 0]

    def search_semantic(self, query: str, top_k: int = 50) -> List[Tuple[int, float]]:
        """
        Búsqueda semántica con embeddings.

        Returns:
            Lista de (índice, score) ordenados por relevancia
        """
        query_embedding = self._encode_query(query)

        # Buscar en FAISS (inner product = cosine con vectores normalizados)
        scores, indices = self.faiss_index.search(query_embedding, top_k)

        return [(int(idx), float(score)) for idx, score in zip(indices[0], scores[0])]

    def rrf_fusion(
        self,
        results_list: List[List[Tuple[int, float]]],
        top_k: int = 10
    ) -> List[Tuple[int, float]]:
        """
        Reciprocal Rank Fusion para combinar rankings.

        RRF_score(d) = sum(1 / (k + rank_i(d))) para cada sistema i

        Args:
            results_list: Lista de resultados de cada sistema [(idx, score), ...]
            top_k: Número de resultados finales

        Returns:
            Lista fusionada de (índice, rrf_score)
        """
        rrf_scores = {}

        for results in results_list:
            for rank, (idx, _) in enumerate(results):
                if idx not in rrf_scores:
                    rrf_scores[idx] = 0.0
                # RRF formula: 1 / (k + rank)
                rrf_scores[idx] += 1.0 / (self.rrf_k + rank + 1)

        # Ordenar por score RRF
        sorted_results = sorted(rrf_scores.items(), key=lambda x: -x[1])

        return sorted_results[:top_k]

    def search(
        self,
        query: str,
        top_k: int = 10,
        bm25_weight: float = 0.5,
        semantic_weight: float = 0.5,
        return_debug: bool = False
    ) -> List[SearchResult]:
        """
        Búsqueda híbrida combinando BM25 + semántica.

        Args:
            query: Texto de búsqueda
            top_k: Número de resultados
            bm25_weight: Peso para BM25 (no usado en RRF puro)
            semantic_weight: Peso para semántica (no usado en RRF puro)
            return_debug: Incluir ranks individuales en resultados

        Returns:
            Lista de SearchResult ordenados por relevancia
        """
        # Búsquedas individuales (obtener más candidatos para fusión)
        bm25_results = self.search_bm25(query, top_k=top_k * 5)
        semantic_results = self.search_semantic(query, top_k=top_k * 5)

        # Crear mapeo de ranks para debug
        bm25_ranks = {idx: rank for rank, (idx, _) in enumerate(bm25_results)}
        semantic_ranks = {idx: rank for rank, (idx, _) in enumerate(semantic_results)}

        # Fusión RRF
        fused_results = self.rrf_fusion([bm25_results, semantic_results], top_k=top_k)

        # Construir resultados
        results = []
        for idx, score in fused_results:
            article = self.articles[idx]
            result = SearchResult(
                article_id=article.get('article_id', f"{article['id_norma']}_art_{article['numero_articulo']}"),
                id_norma=article['id_norma'],
                tipo_norma=article['tipo_norma'],
                numero_norma=article['numero_norma'],
                titulo_norma=article['titulo_norma'],
                numero_articulo=article['numero_articulo'],
                texto=article['texto'],
                score=score,
                bm25_rank=bm25_ranks.get(idx),
                semantic_rank=semantic_ranks.get(idx)
            )
            results.append(result)

        return results

    def search_semantic_only(self, query: str, top_k: int = 10) -> List[SearchResult]:
        """Búsqueda solo semántica (para comparación)."""
        results = self.search_semantic(query, top_k)

        return [
            SearchResult(
                article_id=self.articles[idx].get('article_id', ''),
                id_norma=self.articles[idx]['id_norma'],
                tipo_norma=self.articles[idx]['tipo_norma'],
                numero_norma=self.articles[idx]['numero_norma'],
                titulo_norma=self.articles[idx]['titulo_norma'],
                numero_articulo=self.articles[idx]['numero_articulo'],
                texto=self.articles[idx]['texto'],
                score=score,
                semantic_rank=rank
            )
            for rank, (idx, score) in enumerate(results)
        ]

    def search_bm25_only(self, query: str, top_k: int = 10) -> List[SearchResult]:
        """Búsqueda solo BM25 (para comparación)."""
        results = self.search_bm25(query, top_k)

        return [
            SearchResult(
                article_id=self.articles[idx].get('article_id', ''),
                id_norma=self.articles[idx]['id_norma'],
                tipo_norma=self.articles[idx]['tipo_norma'],
                numero_norma=self.articles[idx]['numero_norma'],
                titulo_norma=self.articles[idx]['titulo_norma'],
                numero_articulo=self.articles[idx]['numero_articulo'],
                texto=self.articles[idx]['texto'],
                score=score,
                bm25_rank=rank
            )
            for rank, (idx, score) in enumerate(results)
        ]


class HybridSearchWithRerank(HybridSearch):
    """
    Búsqueda híbrida con Cross-Encoder reranking.

    Extiende HybridSearch agregando Stage 3: reranking con Cross-Encoder
    para mayor precisión en búsquedas de compliance legal.
    """

    def __init__(
        self,
        index_dir: Path,
        model_name: str = "intfloat/multilingual-e5-base",
        rerank_model: str = "cross-encoder/mmarco-mMiniLMv2-L12-H384-v1",
        rrf_k: int = 60
    ):
        # Inicializar búsqueda híbrida base
        super().__init__(index_dir, model_name, rrf_k)

        # Cargar Cross-Encoder
        try:
            from .reranker import Reranker
        except ImportError:
            from reranker import Reranker
        self.reranker = Reranker(model_name=rerank_model)

    def search_with_rerank(
        self,
        query: str,
        candidates: int = 50,
        threshold: Optional[float] = None,
        top_k: Optional[int] = None
    ) -> List[SearchResult]:
        """
        Búsqueda completa: BM25 + Dense + RRF + Cross-Encoder.

        Args:
            query: Texto de búsqueda
            candidates: Candidatos a pasar al reranker (default 50)
            threshold: Score mínimo del reranker (None = sin filtro)
            top_k: Máximo de resultados (None = todos sobre threshold)

        Returns:
            Lista de SearchResult ordenados por Cross-Encoder score
        """
        # Stage 1+2: Búsqueda híbrida para obtener candidatos
        hybrid_results = self.search(query, top_k=candidates)

        if not hybrid_results:
            return []

        # Preparar textos para reranking
        texts = [r.texto for r in hybrid_results]

        # Stage 3: Reranking con Cross-Encoder
        reranked = self.reranker.rerank(
            query,
            texts,
            threshold=threshold,
            top_k=top_k
        )

        # Construir resultados finales
        results = []
        for idx, rerank_score in reranked:
            original = hybrid_results[idx]
            result = SearchResult(
                article_id=original.article_id,
                id_norma=original.id_norma,
                tipo_norma=original.tipo_norma,
                numero_norma=original.numero_norma,
                titulo_norma=original.titulo_norma,
                numero_articulo=original.numero_articulo,
                texto=original.texto,
                score=rerank_score,  # Usar score del reranker
                bm25_rank=original.bm25_rank,
                semantic_rank=original.semantic_rank,
                rerank_score=rerank_score
            )
            results.append(result)

        return results

    def search_compliance(
        self,
        query: str,
        threshold: float = 0.3,
        group_by_norm: bool = True
    ) -> dict:
        """
        Búsqueda optimizada para compliance legal.

        Retorna todos los artículos relevantes agrupados por norma,
        con información de vinculaciones.

        Args:
            query: Texto de búsqueda
            threshold: Score mínimo (default 0.3)
            group_by_norm: Agrupar resultados por norma

        Returns:
            Dict con resultados agrupados y metadata
        """
        import time
        start = time.perf_counter()

        # Búsqueda con reranking
        results = self.search_with_rerank(
            query,
            candidates=50,
            threshold=threshold
        )

        elapsed = (time.perf_counter() - start) * 1000

        if not group_by_norm:
            return {
                "query": query,
                "total": len(results),
                "latency_ms": round(elapsed, 1),
                "results": results
            }

        # Agrupar por norma
        by_norm = {}
        for r in results:
            key = f"{r.tipo_norma} {r.numero_norma}"
            if key not in by_norm:
                by_norm[key] = {
                    "tipo": r.tipo_norma,
                    "numero": r.numero_norma,
                    "id_norma": r.id_norma,
                    "titulo": r.titulo_norma,
                    "articulos": []
                }
            by_norm[key]["articulos"].append({
                "numero": r.numero_articulo,
                "score": round(r.score, 3),
                "texto": r.texto  # Texto completo
            })

        return {
            "query": query,
            "total_articulos": len(results),
            "total_normas": len(by_norm),
            "latency_ms": round(elapsed, 1),
            "threshold": threshold,
            "normas": by_norm
        }


class GraphEnhancedSearch(HybridSearchWithRerank):
    """
    Búsqueda híbrida + reranking + boost por grafo de normas.

    Usa el grafo para:
    1. Boost a normas que definen conceptos mencionados en la query
    2. Boost a normas relacionadas (referenciadas por las definitorias)
    """

    @staticmethod
    def _razon_boost(boost: float, clase: str) -> str:
        """Razón del boost según tipo de norma y nivel de boost."""
        if boost >= 2.0:
            if clase == 'reglamento_base':
                return 'define concepto'
            elif clase == 'fija_valores':
                return 'aplica concepto'
            elif clase == 'modifica':
                return 'modifica definición'
            return 'menciona concepto'
        return 'referencia a definitoria'

    def __init__(
        self,
        index_dir: Path,
        graph_dir: Path,
        model_name: str = "intfloat/multilingual-e5-base",
        rerank_model: str = "cross-encoder/mmarco-mMiniLMv2-L12-H384-v1",
        rrf_k: int = 60
    ):
        super().__init__(index_dir, model_name, rerank_model, rrf_k)

        # Cargar grafo
        try:
            from .graph_builder import NormaGraphBuilder, NormaGraphQuery
        except ImportError:
            from graph_builder import NormaGraphBuilder, NormaGraphQuery

        print("Cargando grafo de normas...")
        self.graph = NormaGraphBuilder.cargar(graph_dir)
        self.graph_query = NormaGraphQuery(self.graph)
        n_nodos = self.graph.number_of_nodes()
        n_aristas = self.graph.number_of_edges()
        print(f"  - Grafo: {n_nodos} nodos, {n_aristas} aristas")

    def _find_articles_by_norma(self, id_norma: str, max_articles: int = 3) -> List[int]:
        """Encuentra índices de artículos que pertenecen a una norma específica."""
        indices = []
        for idx, article in enumerate(self.articles):
            if article.get('id_norma') == id_norma:
                indices.append(idx)
                if len(indices) >= max_articles:
                    break
        return indices

    def search_with_graph(
        self,
        query: str,
        candidates: int = 50,
        threshold: Optional[float] = None,
        top_k: Optional[int] = None,
        graph_boost: bool = True
    ) -> List[SearchResult]:
        """
        Búsqueda completa: BM25 + Dense + RRF + Cross-Encoder + Graph boost.

        El grafo hace dos cosas:
        1. INYECTA artículos de normas relevantes al pool de candidatos
        2. Aplica boost al score final
        """
        # Stage 0: Consultar grafo ANTES de buscar
        boosts = {}
        graph_norma_ids = set()
        if graph_boost:
            boosts = self.graph_query.contexto_para_query(query)
            graph_norma_ids = {nid for nid, b in boosts.items() if b >= 2.0}

        # Stage 1-3: Búsqueda híbrida con reranking
        results = self.search_with_rerank(query, candidates, threshold, top_k=None)

        # Stage 3.5: Inyectar artículos de normas del grafo si no están en resultados
        if graph_norma_ids:
            normas_en_resultados = {r.id_norma for r in results}
            normas_faltantes = graph_norma_ids - normas_en_resultados

            if normas_faltantes:
                # Buscar artículos de estas normas y reranquearlos
                inject_indices = []
                for nid in normas_faltantes:
                    inject_indices.extend(self._find_articles_by_norma(nid, max_articles=5))

                if inject_indices:
                    # Reranquear los artículos inyectados
                    inject_texts = [self.articles[idx]['texto'] for idx in inject_indices]
                    reranked = self.reranker.rerank(query, inject_texts, threshold=threshold)

                    for orig_idx, rerank_score in reranked:
                        art_idx = inject_indices[orig_idx]
                        article = self.articles[art_idx]
                        results.append(SearchResult(
                            article_id=article.get('article_id', ''),
                            id_norma=article['id_norma'],
                            tipo_norma=article['tipo_norma'],
                            numero_norma=article['numero_norma'],
                            titulo_norma=article['titulo_norma'],
                            numero_articulo=article['numero_articulo'],
                            texto=article['texto'],
                            score=rerank_score,
                            rerank_score=rerank_score,
                        ))

        # Stage 4: Graph boost
        if boosts:
            for result in results:
                boost_factor = boosts.get(result.id_norma, 1.0)
                result.score = result.score * boost_factor

            results.sort(key=lambda r: r.score, reverse=True)

        return results[:top_k] if top_k else results

    def search_compliance_with_graph(
        self,
        query: str,
        threshold: float = -3.0,
        group_by_norm: bool = True
    ) -> dict:
        """
        Compliance search con graph boost.
        """
        import time
        start = time.perf_counter()

        results = self.search_with_graph(
            query,
            candidates=50,
            threshold=threshold
        )

        elapsed = (time.perf_counter() - start) * 1000

        # Info del grafo para la query
        boosts = self.graph_query.contexto_para_query(query)
        graph_info = {}
        for id_norma, boost in boosts.items():
            if boost > 1.0:
                node = self.graph.nodes.get(id_norma, {})
                clase = node.get('clase', '')
                clase_label = {
                    'reglamento_base': 'Reglamento base',
                    'fija_valores': 'Fija valores',
                    'modifica': 'Modifica',
                    'deroga': 'Deroga',
                }.get(clase, '')
                año = node.get('año', '')
                # Extraer nombre limpio del título
                titulo_raw = node.get('titulo', '')
                # Limpiar duplicados de scraping y prefijo tipo+numero
                nombre = re.sub(r'^[A-ZÁÉÍÓÚÑ]+\s+\d+\s*', '', titulo_raw, count=1).strip()
                nombre = re.sub(r'^[A-ZÁÉÍÓÚÑ]+\s+\d+\s*', '', nombre, count=1).strip()  # segundo duplicado
                nombre = re.sub(r'^T\s+', '', nombre).strip()  # quitar "T " de "13 T FIJA..."
                graph_info[id_norma] = {
                    'boost': boost,
                    'tipo': node.get('tipo', ''),
                    'numero': node.get('numero', ''),
                    'año': año,
                    'clase': clase_label,
                    'nombre': nombre[:120],
                    'razon': self._razon_boost(boost, clase)
                }

        if not group_by_norm:
            return {
                "query": query,
                "total": len(results),
                "latency_ms": round(elapsed, 1),
                "graph_boosts": graph_info,
                "results": results
            }

        # Agrupar por norma
        by_norm = {}
        for r in results:
            key = f"{r.tipo_norma} {r.numero_norma}"
            if key not in by_norm:
                boost_info = graph_info.get(r.id_norma, {})
                # Obtener año y clase del grafo (disponible para todas las normas)
                node_data = self.graph.nodes.get(r.id_norma, {})
                año = boost_info.get('año', '') or node_data.get('año', '')
                clase = boost_info.get('clase', '') or node_data.get('clase', '')
                # Traducir clase interna a label legible
                if clase and clase not in ('Reglamento base', 'Fija valores', 'Modifica', 'Deroga'):
                    clase = {
                        'reglamento_base': 'Reglamento base',
                        'fija_valores': 'Fija valores',
                        'modifica': 'Modifica',
                        'deroga': 'Deroga',
                    }.get(clase, clase)
                # Nombre limpio de la norma
                nombre = boost_info.get('nombre', '')
                if not nombre:
                    titulo_raw = node_data.get('titulo', r.titulo_norma or '')
                    nombre = re.sub(r'^[A-ZÁÉÍÓÚÑ]+\s+\d+\s*', '', titulo_raw, count=1).strip()
                    nombre = re.sub(r'^[A-ZÁÉÍÓÚÑ]+\s+\d+\s*', '', nombre, count=1).strip()
                    nombre = re.sub(r'^T\s+', '', nombre).strip()
                    nombre = nombre[:120]
                by_norm[key] = {
                    "tipo": r.tipo_norma,
                    "numero": r.numero_norma,
                    "id_norma": r.id_norma,
                    "titulo": r.titulo_norma,
                    "nombre": nombre,
                    "graph_boost": boost_info.get('boost', 1.0),
                    "graph_razon": boost_info.get('razon', ''),
                    "graph_año": año,
                    "graph_clase": clase,
                    "articulos": []
                }
            by_norm[key]["articulos"].append({
                "numero": r.numero_articulo,
                "score": round(r.score, 3),
                "texto": r.texto
            })

        # Si el grafo identificó normas relevantes, filtrar normas sin boost
        # que tienen scores mucho menores que las boosteadas (probable ruido léxico)
        if graph_info:
            boosted_scores = []
            unboosted = []
            for key, norm_data in by_norm.items():
                best = max(a['score'] for a in norm_data['articulos'])
                if norm_data['graph_boost'] > 1.0:
                    boosted_scores.append(best)
                else:
                    unboosted.append((key, best))

            if boosted_scores:
                # Si el grafo identificó normas relevantes, solo mostrar
                # normas con boost. Las sin boost son probablemente ruido léxico
                # (ej: "coma" como puntuación vs COMA como sigla técnica)
                filtered = {k: v for k, v in by_norm.items() if v['graph_boost'] > 1.0}
                by_norm = filtered

        # Ordenar: reglamentos base que definen primero, luego por mejor score
        def _sort_key(item):
            key, nd = item
            razon = nd.get('graph_razon', '')
            clase = nd.get('graph_clase', '')
            best_score = max(a['score'] for a in nd['articulos'])
            # Prioridad: define > aplica > menciona > referencia > sin boost
            prioridad = {
                'define concepto': 0,
                'aplica concepto': 1,
                'menciona concepto': 2,
                'modifica definición': 3,
                'referencia a definitoria': 4,
            }.get(razon, 5)
            return (prioridad, -best_score)

        by_norm = dict(sorted(by_norm.items(), key=_sort_key))

        total_arts = sum(len(n['articulos']) for n in by_norm.values())

        return {
            "query": query,
            "total_articulos": total_arts,
            "total_normas": len(by_norm),
            "latency_ms": round(elapsed, 1),
            "threshold": threshold,
            "graph_boosts": graph_info,
            "normas": by_norm
        }


def format_result(result: SearchResult, show_text: bool = True, max_text_len: int = 300) -> str:
    """Formatea un resultado para mostrar en consola."""
    lines = [
        f"[{result.tipo_norma} {result.numero_norma}] Art. {result.numero_articulo}",
        f"  Score: {result.score:.4f}",
    ]

    if result.bm25_rank is not None or result.semantic_rank is not None:
        ranks = []
        if result.bm25_rank is not None:
            ranks.append(f"BM25: #{result.bm25_rank + 1}")
        if result.semantic_rank is not None:
            ranks.append(f"Sem: #{result.semantic_rank + 1}")
        lines.append(f"  Ranks: {', '.join(ranks)}")

    if show_text:
        texto = result.texto[:max_text_len]
        if len(result.texto) > max_text_len:
            texto += "..."
        lines.append(f"  {texto}")

    return "\n".join(lines)


def format_compliance_results(data: dict, full_text: bool = False) -> str:
    """Formatea resultados de compliance para consola."""
    lines = [
        f"\n{'='*70}",
        f"Query: '{data['query']}'",
        f"{'='*70}",
        f"Encontrados: {data['total_articulos']} artículos en {data['total_normas']} normas",
        f"Latencia: {data['latency_ms']}ms | Threshold: {data['threshold']}",
    ]

    # Mostrar graph boosts si existen
    graph_boosts = data.get('graph_boosts', {})
    if graph_boosts:
        lines.append(f"\nGraph boost aplicado:")
        for id_norma, info in graph_boosts.items():
            año = info.get('año', '')
            año_str = f" ({año})" if año else ""
            clase = info.get('clase', '')
            clase_str = f" [{clase}]" if clase else ""
            lines.append(f"  [{info['boost']:.1f}x] {info['tipo']} {info['numero']}{año_str}{clase_str} ({info['razon']})")

    lines.append(f"{'='*70}")

    for norm_key, norm_data in data['normas'].items():
        boost = norm_data.get('graph_boost', 1.0)
        razon = norm_data.get('graph_razon', '')
        año = norm_data.get('graph_año', '')
        clase = norm_data.get('graph_clase', '')
        año_str = f" ({año})" if año else ""
        clase_str = f" [{clase}]" if clase else ""
        boost_str = f" [BOOST {boost:.1f}x: {razon}]" if boost > 1.0 else ""
        id_norma = norm_data.get('id_norma', '')
        url = f"https://www.bcn.cl/leychile/navegar?idNorma={id_norma}" if id_norma else ""

        nombre = norm_data.get('nombre', '')
        nombre_str = f"\n  {nombre}" if nombre else ""
        lines.append(f"\n  {norm_key}{año_str}{clase_str}{boost_str}{nombre_str}")
        if url:
            lines.append(f"  {url}")

        for art in norm_data['articulos']:
            preview = art['texto'][:120].replace('\n', ' ')
            lines.append(f"    [{art['score']:+.2f}] Art. {art['numero']}: {preview}...")

    if data.get('total_articulos', 0) > 0:
        lines.append(f"\nUsa --full para ver texto completo o -o archivo.txt para guardar")

    return "\n".join(lines)


def main():
    """Script interactivo de búsqueda."""
    import argparse

    parser = argparse.ArgumentParser(description='Búsqueda híbrida de normas')
    parser.add_argument(
        '--index-dir',
        type=Path,
        default=Path(__file__).parent.parent.parent / 'data' / 'search_index',
        help='Directorio con índice FAISS'
    )
    parser.add_argument(
        '--query',
        type=str,
        help='Query de búsqueda (si no se especifica, modo interactivo)'
    )
    parser.add_argument(
        '--top-k',
        type=int,
        default=5,
        help='Número de resultados'
    )
    parser.add_argument(
        '--threshold',
        type=float,
        default=-3.0,
        help='Score mínimo para compliance (default -3.0)'
    )
    parser.add_argument(
        '--mode',
        choices=['hybrid', 'bm25', 'semantic', 'rerank', 'compliance'],
        default='hybrid',
        help='Modo de búsqueda'
    )
    parser.add_argument(
        '--no-rerank',
        action='store_true',
        help='Desactivar reranking (más rápido, menos preciso)'
    )
    parser.add_argument(
        '--graph-dir',
        type=Path,
        default=Path(__file__).parent.parent.parent / 'data' / 'norma_graph',
        help='Directorio con grafo de normas'
    )
    parser.add_argument(
        '--no-graph',
        action='store_true',
        help='Desactivar graph boost'
    )
    parser.add_argument(
        '--output', '-o',
        type=str,
        help='Guardar resultados en archivo (ej: resultados.txt)'
    )
    parser.add_argument(
        '--full',
        action='store_true',
        help='Mostrar texto completo de artículos'
    )

    args = parser.parse_args()

    # Inicializar motor
    graph_available = args.graph_dir.exists() and not args.no_graph
    if args.no_rerank or args.mode in ['hybrid', 'bm25', 'semantic']:
        engine = HybridSearch(args.index_dir)
        has_rerank = False
        has_graph = False
    elif graph_available:
        engine = GraphEnhancedSearch(args.index_dir, args.graph_dir)
        has_rerank = True
        has_graph = True
    else:
        engine = HybridSearchWithRerank(args.index_dir)
        has_rerank = True
        has_graph = False

    if args.query:
        # Búsqueda única
        if args.mode == 'compliance' and has_graph:
            data = engine.search_compliance_with_graph(args.query, threshold=args.threshold)
            output = format_compliance_results(data, full_text=args.full)
            print(output)
            if args.output:
                with open(args.output, 'w', encoding='utf-8') as f:
                    f.write(format_compliance_results(data, full_text=True))
                print(f"\n✓ Resultados guardados en: {args.output}")
        elif args.mode == 'compliance' and has_rerank:
            data = engine.search_compliance(args.query, threshold=args.threshold)
            output = format_compliance_results(data, full_text=args.full)
            print(output)
            if args.output:
                with open(args.output, 'w', encoding='utf-8') as f:
                    f.write(format_compliance_results(data, full_text=True))
                print(f"\n✓ Resultados guardados en: {args.output}")
        elif args.mode == 'rerank' and has_rerank:
            results = engine.search_with_rerank(args.query, top_k=args.top_k)
            print(f"\n--- {len(results)} resultados (con rerank) para: '{args.query}' ---\n")
            for i, result in enumerate(results, 1):
                print(f"{i}. {format_result(result)}\n")
        elif args.mode == 'bm25':
            results = engine.search_bm25_only(args.query, top_k=args.top_k)
            print(f"\n--- {len(results)} resultados para: '{args.query}' ---\n")
            for i, result in enumerate(results, 1):
                print(f"{i}. {format_result(result)}\n")
        elif args.mode == 'semantic':
            results = engine.search_semantic_only(args.query, top_k=args.top_k)
            print(f"\n--- {len(results)} resultados para: '{args.query}' ---\n")
            for i, result in enumerate(results, 1):
                print(f"{i}. {format_result(result)}\n")
        else:
            results = engine.search(args.query, top_k=args.top_k)
            print(f"\n--- {len(results)} resultados para: '{args.query}' ---\n")
            for i, result in enumerate(results, 1):
                print(f"{i}. {format_result(result)}\n")
        return

    # Modo interactivo
    print("\n" + "="*60)
    print("BÚSQUEDA DE NORMAS ELÉCTRICAS BCN")
    print("="*60)
    if has_graph:
        print("Modos: /bm25, /semantic, /hybrid, /rerank, /compliance, /graph")
        print("Graph boost: ACTIVADO")
    elif has_rerank:
        print("Modos: /bm25, /semantic, /hybrid, /rerank, /compliance")
    else:
        print("Modos: /bm25, /semantic, /hybrid")
        print("(usa --mode rerank o --mode compliance para activar reranking)")
    print("Escribe 'salir' para terminar\n")

    mode = args.mode

    while True:
        try:
            query = input(f"[{mode}] > ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n¡Hasta luego!")
            break

        if not query:
            continue

        if query.lower() == 'salir':
            break

        if query.startswith('/'):
            cmd = query[1:].lower()
            valid_modes = ['bm25', 'semantic', 'hybrid']
            if has_rerank:
                valid_modes.extend(['rerank', 'compliance'])
            if cmd in valid_modes:
                mode = cmd
                print(f"Modo cambiado a: {mode}")
            continue

        # Ejecutar búsqueda según modo
        if mode in ('compliance', 'graph') and has_graph:
            data = engine.search_compliance_with_graph(query, threshold=args.threshold)
            print(format_compliance_results(data))
        elif mode == 'compliance' and has_rerank:
            data = engine.search_compliance(query, threshold=args.threshold)
            print(format_compliance_results(data))
        elif mode == 'rerank' and has_rerank:
            results = engine.search_with_rerank(query, top_k=args.top_k)
            print(f"\n--- {len(results)} resultados (reranked) ---\n")
            for i, result in enumerate(results, 1):
                print(f"{i}. {format_result(result)}\n")
        elif mode == 'bm25':
            results = engine.search_bm25_only(query, top_k=args.top_k)
            print(f"\n--- {len(results)} resultados ---\n")
            for i, result in enumerate(results, 1):
                print(f"{i}. {format_result(result)}\n")
        elif mode == 'semantic':
            results = engine.search_semantic_only(query, top_k=args.top_k)
            print(f"\n--- {len(results)} resultados ---\n")
            for i, result in enumerate(results, 1):
                print(f"{i}. {format_result(result)}\n")
        else:
            results = engine.search(query, top_k=args.top_k)
            print(f"\n--- {len(results)} resultados ---\n")
            for i, result in enumerate(results, 1):
                print(f"{i}. {format_result(result)}\n")


if __name__ == '__main__':
    main()
