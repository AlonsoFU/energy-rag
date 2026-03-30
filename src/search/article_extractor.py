"""
Extractor de artículos desde normas legales chilenas.

Parsea el texto completo de cada norma y extrae artículos individuales
manteniendo la metadata de la norma padre.
"""

import json
import re
from pathlib import Path
from typing import Dict, List, Optional
from dataclasses import dataclass, asdict


@dataclass
class Article:
    """Representa un artículo extraído de una norma."""
    id_norma: str
    tipo_norma: str
    numero_norma: str
    titulo_norma: str
    numero_articulo: str
    texto: str
    # ID único para el artículo: {id_norma}_art_{numero}
    article_id: str = ""

    def __post_init__(self):
        if not self.article_id:
            self.article_id = f"{self.id_norma}_art_{self.numero_articulo}"


class ArticleExtractor:
    """Extrae artículos individuales de normas legales."""

    # Patrones para detectar artículos
    ARTICLE_PATTERNS = [
        # "Artículo 1.-", "Artículo 1°.-", "Artículo 1º.-"
        r'Art[íi]culo\s+(\d+)(?:º|°|o)?(?:\s*bis|\s*ter|\s*quáter)?[\.\-:\s]',
        # "Art. 1.-", "Art. 1°"
        r'Art\.\s*(\d+)(?:º|°|o)?(?:\s*bis|\s*ter|\s*quáter)?[\.\-:\s]',
        # "ARTÍCULO 1" (mayúsculas)
        r'ART[ÍI]CULO\s+(\d+)(?:º|°|o)?(?:\s*bis|\s*ter|\s*quáter)?[\.\-:\s]',
    ]

    # Patrón combinado
    COMBINED_PATTERN = re.compile(
        '|'.join(f'({p})' for p in ARTICLE_PATTERNS),
        re.IGNORECASE | re.MULTILINE
    )

    # Patrón simple para encontrar inicio de artículos
    SIMPLE_PATTERN = re.compile(
        r'(Art[íi]culo\s+\d+(?:º|°|o)?(?:\s*bis|\s*ter|\s*quáter)?)',
        re.IGNORECASE
    )

    def __init__(self, min_article_length: int = 50):
        self.min_article_length = min_article_length

    def extract_articles_from_text(self, text: str) -> List[Dict[str, str]]:
        """
        Extrae artículos del texto completo de una norma.

        Returns:
            Lista de dicts con {numero, texto} por cada artículo
        """
        if not text or len(text) < self.min_article_length:
            return []

        articles = []

        # Encontrar todas las posiciones de inicio de artículos
        matches = list(self.SIMPLE_PATTERN.finditer(text))

        if not matches:
            return []

        for i, match in enumerate(matches):
            # Extraer número del artículo
            article_header = match.group(1)
            num_match = re.search(r'(\d+(?:\s*bis|\s*ter|\s*quáter)?)', article_header, re.IGNORECASE)
            if not num_match:
                continue

            article_num = num_match.group(1).strip()

            # Determinar inicio y fin del texto del artículo
            start = match.start()
            if i + 1 < len(matches):
                end = matches[i + 1].start()
            else:
                # Último artículo: tomar hasta el final o hasta sección siguiente
                end = self._find_section_end(text, start)

            article_text = text[start:end].strip()

            # Limpiar texto
            article_text = self._clean_article_text(article_text)

            if len(article_text) >= self.min_article_length:
                articles.append({
                    'numero': article_num,
                    'texto': article_text
                })

        return articles

    def _find_section_end(self, text: str, start: int) -> int:
        """Encuentra el final de la sección actual."""
        # Buscar patrones que indican fin de sección
        end_patterns = [
            r'\n\s*TÍTULO\s+[IVX\d]+',
            r'\n\s*CAPÍTULO\s+[IVX\d]+',
            r'\n\s*DISPOSICIONES?\s+TRANSITORIAS?',
            r'\n\s*ARTÍCULOS?\s+TRANSITORIOS?',
        ]

        min_end = len(text)
        for pattern in end_patterns:
            match = re.search(pattern, text[start:], re.IGNORECASE)
            if match:
                potential_end = start + match.start()
                if potential_end > start and potential_end < min_end:
                    min_end = potential_end

        return min_end

    def _clean_article_text(self, text: str) -> str:
        """Limpia el texto del artículo."""
        # Remover múltiples espacios en blanco
        text = re.sub(r'\s+', ' ', text)
        # Remover caracteres de control
        text = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]', '', text)
        return text.strip()

    def extract_from_norm_file(self, norm_path: Path) -> List[Article]:
        """
        Extrae artículos de un archivo JSON de norma.

        Args:
            norm_path: Path al archivo JSON de la norma

        Returns:
            Lista de objetos Article
        """
        with open(norm_path, 'r', encoding='utf-8') as f:
            norm_data = json.load(f)

        texto = norm_data.get('texto_completo', '')
        if not texto:
            return []

        raw_articles = self.extract_articles_from_text(texto)

        articles = []
        for raw in raw_articles:
            article = Article(
                id_norma=norm_data.get('id_norma', ''),
                tipo_norma=norm_data.get('tipo', ''),
                numero_norma=norm_data.get('numero', ''),
                titulo_norma=norm_data.get('titulo', ''),
                numero_articulo=raw['numero'],
                texto=raw['texto']
            )
            articles.append(article)

        return articles

    def extract_from_directory(self, normas_dir: Path) -> List[Article]:
        """
        Extrae artículos de todas las normas en un directorio.

        Args:
            normas_dir: Directorio con subcarpetas (decretos/, leyes/, etc.)

        Returns:
            Lista de todos los artículos extraídos
        """
        all_articles = []

        # Buscar todos los JSON en subdirectorios
        for subdir in normas_dir.iterdir():
            if not subdir.is_dir():
                continue

            for json_file in subdir.glob('*.json'):
                if json_file.name == 'relaciones_con_id.json':
                    continue

                try:
                    articles = self.extract_from_norm_file(json_file)
                    all_articles.extend(articles)
                except Exception as e:
                    print(f"Error procesando {json_file}: {e}")

        return all_articles

    def save_articles(self, articles: List[Article], output_path: Path):
        """Guarda artículos extraídos en JSON."""
        data = [asdict(a) for a in articles]
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        print(f"Guardados {len(articles)} artículos en {output_path}")


def main():
    """Script principal para extraer artículos."""
    import argparse

    parser = argparse.ArgumentParser(description='Extrae artículos de normas legales')
    parser.add_argument(
        '--input-dir',
        type=Path,
        default=Path(__file__).parent.parent.parent / 'data' / 'normas_completas',
        help='Directorio con normas (default: data/normas_completas)'
    )
    parser.add_argument(
        '--output',
        type=Path,
        default=Path(__file__).parent.parent.parent / 'data' / 'articulos_extraidos.json',
        help='Archivo de salida (default: data/articulos_extraidos.json)'
    )

    args = parser.parse_args()

    print(f"Extrayendo artículos de: {args.input_dir}")

    extractor = ArticleExtractor()
    articles = extractor.extract_from_directory(args.input_dir)

    print(f"\nEstadísticas:")
    print(f"  - Artículos extraídos: {len(articles)}")

    # Estadísticas por tipo de norma
    by_type = {}
    for a in articles:
        by_type[a.tipo_norma] = by_type.get(a.tipo_norma, 0) + 1

    for tipo, count in sorted(by_type.items(), key=lambda x: -x[1]):
        print(f"  - {tipo}: {count} artículos")

    extractor.save_articles(articles, args.output)


if __name__ == '__main__':
    main()
