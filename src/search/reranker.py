"""
Cross-Encoder Reranker para búsqueda de normas legales.

Reordena los candidatos usando un modelo que lee query+documento juntos
para mayor precisión en compliance legal.
"""

from typing import List, Tuple, Optional
from dataclasses import dataclass

try:
    from sentence_transformers import CrossEncoder
except ImportError:
    print("Instalando sentence-transformers...")
    import subprocess
    subprocess.run(["pip", "install", "sentence-transformers", "-q"])
    from sentence_transformers import CrossEncoder


@dataclass
class RerankResult:
    """Resultado de reranking."""
    index: int
    score: float
    texto: str
    metadata: dict


class Reranker:
    """
    Cross-Encoder para reranking de resultados de búsqueda.

    Usa un modelo que procesa (query, documento) juntos para
    evaluar relevancia con mayor precisión.
    """

    # Modelo entrenado en español (mMARCO)
    DEFAULT_MODEL = "cross-encoder/mmarco-mMiniLMv2-L12-H384-v1"

    def __init__(
        self,
        model_name: str = DEFAULT_MODEL,
        device: Optional[str] = None,
        max_length: int = 512
    ):
        """
        Args:
            model_name: Modelo de cross-encoder
            device: 'cuda', 'cpu' o None (auto)
            max_length: Máximo de tokens por par query-doc
        """
        print(f"Cargando Cross-Encoder: {model_name}")
        self.model = CrossEncoder(model_name, max_length=max_length, device=device)
        self.model_name = model_name
        print("✓ Cross-Encoder listo")

    def rerank(
        self,
        query: str,
        documents: List[str],
        top_k: Optional[int] = None,
        threshold: Optional[float] = None
    ) -> List[Tuple[int, float]]:
        """
        Reordena documentos por relevancia al query.

        Args:
            query: Texto de búsqueda
            documents: Lista de textos de documentos
            top_k: Retornar solo los mejores K (None = todos)
            threshold: Retornar solo los que superen este score (None = todos)

        Returns:
            Lista de (índice_original, score) ordenados por relevancia
        """
        if not documents:
            return []

        # Crear pares (query, doc) para el modelo
        pairs = [(query, doc) for doc in documents]

        # Obtener scores
        scores = self.model.predict(pairs, show_progress_bar=False)

        # Crear lista de (índice, score)
        indexed_scores = [(i, float(score)) for i, score in enumerate(scores)]

        # Ordenar por score descendente
        indexed_scores.sort(key=lambda x: x[1], reverse=True)

        # Aplicar filtros
        if threshold is not None:
            indexed_scores = [(i, s) for i, s in indexed_scores if s > threshold]

        if top_k is not None:
            indexed_scores = indexed_scores[:top_k]

        return indexed_scores

    def rerank_with_metadata(
        self,
        query: str,
        documents: List[dict],
        text_key: str = "texto",
        top_k: Optional[int] = None,
        threshold: Optional[float] = None
    ) -> List[RerankResult]:
        """
        Reordena documentos manteniendo metadata.

        Args:
            query: Texto de búsqueda
            documents: Lista de dicts con 'texto' y metadata
            text_key: Key del texto en cada dict
            top_k: Retornar solo los mejores K
            threshold: Score mínimo

        Returns:
            Lista de RerankResult ordenados por relevancia
        """
        texts = [doc[text_key] for doc in documents]
        reranked = self.rerank(query, texts, top_k=top_k, threshold=threshold)

        results = []
        for idx, score in reranked:
            results.append(RerankResult(
                index=idx,
                score=score,
                texto=documents[idx][text_key],
                metadata=documents[idx]
            ))

        return results


def main():
    """Test del reranker."""
    print("Probando Cross-Encoder Reranker...")

    reranker = Reranker()

    query = "tasa de interés por mora en pagos"

    documents = [
        "La potencia instalada se calcula según el artículo 5.",
        "En caso de atraso en los pagos, se aplicará el interés corriente incrementado en 50%.",
        "El balance de potencia considera las transferencias entre generadores.",
        "Las reliquidaciones deberán ser pagadas aplicando la tasa de interés corriente.",
        "La energía eléctrica se mide en kilowatts hora.",
    ]

    print(f"\nQuery: '{query}'")
    print("\nDocumentos originales:")
    for i, doc in enumerate(documents):
        print(f"  {i}: {doc[:60]}...")

    results = reranker.rerank(query, documents)

    print("\nDespués de reranking:")
    for idx, score in results:
        print(f"  [{score:.3f}] Doc {idx}: {documents[idx][:60]}...")


if __name__ == "__main__":
    main()
