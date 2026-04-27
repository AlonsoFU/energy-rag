"""DEPRECATED. Replaced by src/pipelines/, src/components/, src/extraction/.
Kept for transition period; will be removed in v1.1.

Generador de embeddings para artículos de normas legales.

Usa multilingual-e5-base para generar embeddings y FAISS para indexación.
"""

import json
import pickle
from pathlib import Path
from typing import List, Dict, Optional
import numpy as np

try:
    from sentence_transformers import SentenceTransformer
    import faiss
except ImportError:
    print("Instalando dependencias...")
    import subprocess
    subprocess.run(["pip", "install", "sentence-transformers", "faiss-cpu", "-q"])
    from sentence_transformers import SentenceTransformer
    import faiss

from tqdm import tqdm


class EmbeddingGenerator:
    """Genera embeddings y crea índice FAISS para búsqueda semántica."""

    # Modelo recomendado para español (278M parámetros, ~1.1GB VRAM)
    DEFAULT_MODEL = "intfloat/multilingual-e5-base"

    def __init__(
        self,
        model_name: str = DEFAULT_MODEL,
        device: Optional[str] = None,
        batch_size: int = 32
    ):
        """
        Args:
            model_name: Nombre del modelo de sentence-transformers
            device: 'cuda', 'cpu' o None (auto-detect)
            batch_size: Tamaño de batch para encoding
        """
        self.model_name = model_name
        self.batch_size = batch_size

        print(f"Cargando modelo: {model_name}")
        self.model = SentenceTransformer(model_name, device=device)
        self.dimension = self.model.get_sentence_embedding_dimension()
        print(f"Dimensión de embeddings: {self.dimension}")

    def generate_embeddings(
        self,
        texts: List[str],
        prefix: str = "passage: ",
        show_progress: bool = True
    ) -> np.ndarray:
        """
        Genera embeddings para una lista de textos.

        Args:
            texts: Lista de textos a procesar
            prefix: Prefijo para e5 models ("passage: " para documentos, "query: " para queries)
            show_progress: Mostrar barra de progreso

        Returns:
            Array numpy de embeddings (n_texts, dimension)
        """
        # e5 models requieren prefijo
        if 'e5' in self.model_name.lower():
            texts = [f"{prefix}{t}" for t in texts]

        embeddings = self.model.encode(
            texts,
            batch_size=self.batch_size,
            show_progress_bar=show_progress,
            convert_to_numpy=True,
            normalize_embeddings=True  # Importante para cosine similarity
        )

        return embeddings

    def create_faiss_index(self, embeddings: np.ndarray) -> faiss.Index:
        """
        Crea un índice FAISS para búsqueda rápida.

        Args:
            embeddings: Array de embeddings normalizados

        Returns:
            Índice FAISS
        """
        # Para <10K vectores, Flat index es suficiente y exacto
        # Para >100K, usar IVF
        n_vectors = embeddings.shape[0]

        if n_vectors < 10000:
            # Inner product (equivalente a cosine con vectores normalizados)
            index = faiss.IndexFlatIP(self.dimension)
        else:
            # IVF para datasets más grandes
            nlist = min(int(np.sqrt(n_vectors)), 100)
            quantizer = faiss.IndexFlatIP(self.dimension)
            index = faiss.IndexIVFFlat(quantizer, self.dimension, nlist)
            index.train(embeddings)

        index.add(embeddings)
        print(f"Índice FAISS creado con {index.ntotal} vectores")
        return index

    def save_index(
        self,
        index: faiss.Index,
        articles: List[Dict],
        output_dir: Path
    ):
        """
        Guarda índice FAISS y metadata de artículos.

        Args:
            index: Índice FAISS
            articles: Lista de artículos (metadata)
            output_dir: Directorio de salida
        """
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

        # Guardar índice FAISS
        faiss_path = output_dir / "articles.faiss"
        faiss.write_index(index, str(faiss_path))
        print(f"Índice guardado en: {faiss_path}")

        # Guardar metadata de artículos (para mapear índice -> artículo)
        metadata_path = output_dir / "articles_metadata.pkl"
        with open(metadata_path, 'wb') as f:
            pickle.dump(articles, f)
        print(f"Metadata guardada en: {metadata_path}")

        # Guardar info del modelo
        info = {
            'model_name': self.model_name,
            'dimension': self.dimension,
            'n_articles': len(articles)
        }
        info_path = output_dir / "index_info.json"
        with open(info_path, 'w') as f:
            json.dump(info, f, indent=2)

    @classmethod
    def load_index(cls, index_dir: Path):
        """
        Carga índice FAISS y metadata.

        Returns:
            (index, articles, info)
        """
        index_dir = Path(index_dir)

        index = faiss.read_index(str(index_dir / "articles.faiss"))

        with open(index_dir / "articles_metadata.pkl", 'rb') as f:
            articles = pickle.load(f)

        with open(index_dir / "index_info.json", 'r') as f:
            info = json.load(f)

        return index, articles, info


def main():
    """Script principal para generar embeddings."""
    import argparse

    parser = argparse.ArgumentParser(description='Genera embeddings de artículos')
    parser.add_argument(
        '--input',
        type=Path,
        default=Path(__file__).parent.parent.parent / 'data' / 'articulos_extraidos.json',
        help='Archivo JSON con artículos extraídos'
    )
    parser.add_argument(
        '--output-dir',
        type=Path,
        default=Path(__file__).parent.parent.parent / 'data' / 'search_index',
        help='Directorio de salida para índice FAISS'
    )
    parser.add_argument(
        '--model',
        type=str,
        default=EmbeddingGenerator.DEFAULT_MODEL,
        help='Modelo de embeddings'
    )
    parser.add_argument(
        '--batch-size',
        type=int,
        default=32,
        help='Batch size para encoding'
    )

    args = parser.parse_args()

    # Cargar artículos
    print(f"Cargando artículos de: {args.input}")
    with open(args.input, 'r', encoding='utf-8') as f:
        articles = json.load(f)

    print(f"Total artículos: {len(articles)}")

    # Preparar textos
    texts = [a['texto'] for a in articles]

    # Generar embeddings
    generator = EmbeddingGenerator(
        model_name=args.model,
        batch_size=args.batch_size
    )

    print("\nGenerando embeddings...")
    embeddings = generator.generate_embeddings(texts)
    print(f"Shape de embeddings: {embeddings.shape}")

    # Crear índice FAISS
    print("\nCreando índice FAISS...")
    index = generator.create_faiss_index(embeddings)

    # Guardar
    generator.save_index(index, articles, args.output_dir)

    print("\n✓ Embeddings generados exitosamente")
    print(f"  - Artículos: {len(articles)}")
    print(f"  - Dimensión: {generator.dimension}")
    print(f"  - Índice: {args.output_dir}")


if __name__ == '__main__':
    main()
