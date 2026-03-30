"""
Extractor automático de conceptos legales.

Extrae conceptos y relaciones de normas usando:
1. TF-IDF para términos importantes
2. Patrones para detectar definiciones
3. Coocurrencia para relaciones norma-concepto

Sin LLM, sin revisión manual.
"""

import json
import re
import pickle
from pathlib import Path
from typing import Dict, List, Set, Tuple
from collections import Counter, defaultdict
from dataclasses import dataclass, asdict
import math

try:
    from sklearn.feature_extraction.text import TfidfVectorizer
    import numpy as np
except ImportError:
    print("Instalando sklearn...")
    import subprocess
    subprocess.run(["pip", "install", "scikit-learn", "-q"])
    from sklearn.feature_extraction.text import TfidfVectorizer
    import numpy as np


@dataclass
class Concepto:
    """Un concepto extraído automáticamente."""
    termino: str
    definido_en: List[str]  # IDs de normas que lo definen
    usado_en: List[str]     # IDs de normas que lo usan
    frecuencia: int         # Veces que aparece en total
    score_importancia: float  # TF-IDF promedio


@dataclass
class NormaConceptos:
    """Conceptos asociados a una norma."""
    id_norma: str
    tipo: str
    numero: str
    conceptos_definidos: List[str]  # Conceptos que esta norma DEFINE
    conceptos_usados: List[str]     # Conceptos que esta norma USA
    es_norma_definitoria: bool      # True si define muchos conceptos


class ConceptExtractor:
    """Extrae conceptos automáticamente de normas legales."""

    # Patrones para detectar definiciones
    PATRONES_DEFINICION = [
        # "Se entenderá por X..."
        r'[Ss]e entender[áa] por ["\']?([A-ZÁÉÍÓÚÑ][A-Za-záéíóúñ\s]{2,40})["\']?',
        # "Para efectos de este reglamento, X significa..."
        r'[Pp]ara (?:los )?efectos de (?:este|la presente|el presente)[^,:.]{0,30}[,:]\s*["\']?([A-ZÁÉÍÓÚÑ][A-Za-záéíóúñ\s]{2,40})["\']?',
        # "X: significa..." o "X: es..."
        r'([A-ZÁÉÍÓÚÑ][A-Za-záéíóúñ\s]{2,30})[,:]\s*(?:significa|es|corresponde a|se define como)',
        # "La definición de X"
        r'[Ll]a definici[óo]n de ["\']?([A-ZÁÉÍÓÚÑ][A-Za-záéíóúñ\s]{2,40})["\']?',
        # Siglas en mayúsculas seguidas de definición
        r'([A-Z]{2,10})[,:]\s*(?:significa|es el|es la|corresponde)',
    ]

    # Patrones para detectar siglas/acrónimos (probablemente conceptos técnicos)
    PATRON_SIGLA = re.compile(r'\b([A-Z]{2,10})\b')

    # Stopwords para filtrar términos no relevantes
    STOPWORDS_LEGAL = {
        # Preposiciones y artículos
        'de', 'del', 'la', 'las', 'el', 'los', 'un', 'una', 'unos', 'unas',
        'en', 'con', 'por', 'para', 'sin', 'sobre', 'entre', 'hacia', 'desde',
        'que', 'cual', 'quien', 'cuyo', 'cuya', 'cuyos', 'cuyas',
        'este', 'esta', 'estos', 'estas', 'ese', 'esa', 'esos', 'esas',
        'aquel', 'aquella', 'aquellos', 'aquellas', 'esto', 'eso', 'aquello',
        'su', 'sus', 'mi', 'mis', 'tu', 'tus', 'se', 'si', 'no', 'ni',
        'como', 'cuando', 'donde', 'porque', 'pero', 'sino', 'aunque',
        'cada', 'todo', 'toda', 'todos', 'todas', 'otro', 'otra', 'otros', 'otras',
        'mismo', 'misma', 'mismos', 'mismas', 'tal', 'tales', 'tanto', 'tanta',
        'más', 'mas', 'menos', 'muy', 'mucho', 'mucha', 'muchos', 'muchas',
        'poco', 'poca', 'pocos', 'pocas', 'algún', 'alguna', 'algunos', 'algunas',
        'ningún', 'ninguna', 'ningunos', 'ningunas', 'ya', 'aún', 'aun',
        # Verbos auxiliares y comunes
        'ser', 'estar', 'haber', 'tener', 'poder', 'deber', 'hacer',
        'será', 'serán', 'sea', 'sean', 'sido', 'siendo', 'fue', 'fueron',
        'está', 'están', 'esté', 'estén', 'estado', 'estando', 'estuvo',
        'ha', 'han', 'hay', 'haya', 'hayan', 'habido', 'habiendo', 'hubo',
        'tiene', 'tienen', 'tenga', 'tengan', 'tenido', 'teniendo', 'tuvo',
        'puede', 'pueden', 'pueda', 'puedan', 'podido', 'pudiendo', 'pudo',
        'debe', 'deben', 'deba', 'deban', 'debido', 'debiendo', 'debió',
        'hace', 'hacen', 'haga', 'hagan', 'hecho', 'haciendo', 'hizo',
        'son', 'era', 'eran', 'sería', 'serían', 'fuera', 'fueran',
        # Términos legales genéricos
        'artículo', 'articulo', 'decreto', 'ley', 'resolución', 'resolucion',
        'inciso', 'numeral', 'párrafo', 'parrafo', 'título', 'titulo',
        'capítulo', 'capitulo', 'disposición', 'disposicion', 'transitorio',
        'siguiente', 'presente', 'anterior', 'posterior', 'dicho', 'dicha',
        'establecido', 'establecida', 'señalado', 'señalada', 'indicado', 'indicada',
        'dispuesto', 'dispuesta', 'contenido', 'contenida', 'previsto', 'prevista',
        'conforme', 'según', 'segun', 'acuerdo', 'virtud', 'efecto', 'caso',
        'forma', 'manera', 'modo', 'través', 'traves', 'medio', 'plazo', 'fecha',
        'año', 'años', 'mes', 'meses', 'día', 'dias', 'días',
        'enero', 'febrero', 'marzo', 'abril', 'mayo', 'junio', 'julio',
        'agosto', 'septiembre', 'octubre', 'noviembre', 'diciembre',
        # Palabras genéricas adicionales
        'parte', 'partes', 'respecto', 'relación', 'relacion', 'materia',
        'objeto', 'fin', 'fines', 'aplicación', 'aplicacion', 'cumplimiento',
        'cuanto', 'cuyo', 'cuya', 'cuyos', 'cuyas', 'cual', 'cuales',
        'también', 'tambien', 'además', 'ademas', 'asi', 'así',
        'solo', 'sólo', 'mientras', 'siempre', 'nunca', 'vez', 'veces',
        'cualquier', 'cualquiera', 'cualesquiera', 'demás', 'demas',
        'primero', 'primera', 'segundo', 'segunda', 'tercero', 'tercera',
        'último', 'ultima', 'nuevo', 'nueva', 'nuevos', 'nuevas',
        'debe', 'deberá', 'debera', 'deberán', 'deberan', 'podrá', 'podra',
        'corresponde', 'corresponden', 'correspondiente', 'correspondientes',
        'respectivo', 'respectiva', 'respectivos', 'respectivas',
        'referido', 'referida', 'referidos', 'referidas', 'mencionado', 'mencionada',
        # Siglas comunes que no son conceptos del dominio
        'etc', 'art', 'inc', 'num', 'pag', 'pp', 're', 'ar', 'te', 'er',
    }

    def __init__(self, min_freq: int = 2, max_conceptos_por_norma: int = 50):
        """
        Args:
            min_freq: Frecuencia mínima para considerar un término
            max_conceptos_por_norma: Máximo de conceptos a extraer por norma
        """
        self.min_freq = min_freq
        self.max_conceptos = max_conceptos_por_norma
        self.conceptos: Dict[str, Concepto] = {}
        self.normas: Dict[str, NormaConceptos] = {}

    def _limpiar_texto(self, texto: str) -> str:
        """Limpia texto para procesamiento."""
        # Remover números de artículos
        texto = re.sub(r'Artículo\s+\d+[°ºo]?', '', texto)
        # Remover fechas
        texto = re.sub(r'\d{1,2}[/-]\d{1,2}[/-]\d{2,4}', '', texto)
        # Remover números solos
        texto = re.sub(r'\b\d+\b', '', texto)
        return texto

    def _extraer_definiciones(self, texto: str) -> List[str]:
        """Extrae términos que son DEFINIDOS en el texto."""
        definiciones = []

        for patron in self.PATRONES_DEFINICION:
            matches = re.findall(patron, texto)
            for match in matches:
                termino = match.strip()
                # Filtrar términos muy cortos o muy largos
                if 2 < len(termino) < 50:
                    # Limpiar y normalizar
                    termino = re.sub(r'\s+', ' ', termino).strip()
                    if termino.lower() not in self.STOPWORDS_LEGAL:
                        definiciones.append(termino)

        return list(set(definiciones))

    def _extraer_siglas(self, texto: str) -> List[str]:
        """Extrae siglas/acrónimos (probables conceptos técnicos)."""
        siglas = self.PATRON_SIGLA.findall(texto)
        # Filtrar siglas comunes que no son conceptos técnicos del dominio
        siglas_excluir = {
            # Tipos de normas
            'DO', 'DFL', 'DS', 'DTO', 'LEY', 'ART', 'INC', 'NUM', 'SEC',
            'RES', 'REG', 'DEC', 'NRO', 'NRO', 'NO', 'DE', 'EN', 'LA', 'EL',
            # Patrones comunes en texto legal
            'TE', 'RE', 'AR', 'ER', 'ES', 'AS', 'OS', 'AL', 'AN', 'OR',
            'LO', 'LE', 'SE', 'ME', 'VE', 'HA', 'HE', 'YA', 'UN', 'SI',
            'II', 'III', 'IV', 'VI', 'VII', 'VIII', 'IX', 'XI', 'XII',
            # Meses abreviados
            'ENE', 'FEB', 'MAR', 'ABR', 'MAY', 'JUN', 'JUL', 'AGO', 'SEP', 'OCT', 'NOV', 'DIC',
            # Fragmentos comunes sin significado
            'PAR', 'GEN', 'CER', 'DIA', 'ANT', 'ANTE', 'POST', 'PRE',
            'QUE', 'CON', 'SIN', 'POR', 'DEL', 'LAS', 'LOS', 'UNA',
            'MAS', 'PARA', 'COMO', 'CADA', 'TODO', 'OTRA', 'SOBRE',
            # Palabras legales genéricas en mayúsculas
            'NOTA', 'FIJA', 'TITULO', 'GENERAL', 'GENERALES', 'SUPREMO',
            'APRUEBA', 'ESTABLECE', 'MODIFICA', 'REGLAMENTO', 'INDICA',
            'MINISTERIO', 'SERVICIO', 'SERVICIOS', 'NACIONAL',
        }
        # Requiere mínimo 3 caracteres para siglas extraídas por este método
        return [s for s in set(siglas) if s not in siglas_excluir and len(s) >= 3]

    def _extraer_terminos_tfidf(
        self,
        textos: List[str],
        ids: List[str],
        top_n: int = 30
    ) -> Dict[str, List[Tuple[str, float]]]:
        """
        Extrae términos importantes por documento usando TF-IDF.

        Returns:
            Dict de id_norma -> [(termino, score), ...]
        """
        # Configurar vectorizador - tokens de 4+ caracteres para evitar stopwords
        vectorizer = TfidfVectorizer(
            ngram_range=(1, 3),  # Unigramas, bigramas, trigramas
            max_features=5000,
            min_df=self.min_freq,
            max_df=0.7,  # Ignorar términos en >70% de docs (más agresivo)
            token_pattern=r'(?u)\b[A-Za-záéíóúñÁÉÍÓÚÑ]{4,}\b',  # 4+ caracteres
            stop_words=list(self.STOPWORDS_LEGAL),  # Aplicar stopwords
        )

        try:
            tfidf_matrix = vectorizer.fit_transform(textos)
        except ValueError:
            # Muy pocos documentos
            return {id_: [] for id_ in ids}

        feature_names = vectorizer.get_feature_names_out()

        resultados = {}
        for idx, id_norma in enumerate(ids):
            # Obtener scores para este documento
            scores = tfidf_matrix[idx].toarray().flatten()

            # Top N términos
            top_indices = scores.argsort()[-top_n:][::-1]
            terminos = [
                (feature_names[i], float(scores[i]))
                for i in top_indices
                if scores[i] > 0 and feature_names[i].lower() not in self.STOPWORDS_LEGAL
            ]

            resultados[id_norma] = terminos

        return resultados

    def _calcular_coocurrencia(
        self,
        textos: List[str],
        ids: List[str],
        conceptos: Set[str]
    ) -> Dict[str, Dict[str, int]]:
        """
        Calcula coocurrencia de conceptos en cada norma.

        Returns:
            Dict de concepto -> {id_norma: frecuencia}
        """
        coocurrencia = defaultdict(lambda: defaultdict(int))

        for texto, id_norma in zip(textos, ids):
            texto_lower = texto.lower()
            for concepto in conceptos:
                # Contar ocurrencias del concepto en esta norma
                count = texto_lower.count(concepto.lower())
                if count > 0:
                    coocurrencia[concepto][id_norma] = count

        return dict(coocurrencia)

    def extraer_de_normas(self, normas_dir: Path) -> Dict[str, Concepto]:
        """
        Extrae conceptos de todas las normas en un directorio.

        Args:
            normas_dir: Directorio con subcarpetas (decretos/, leyes/, etc.)

        Returns:
            Dict de termino -> Concepto
        """
        print("Cargando normas...")

        # Cargar todas las normas
        textos = []
        ids = []
        metadatos = {}

        for subdir in normas_dir.iterdir():
            if not subdir.is_dir():
                continue

            for json_file in subdir.glob('*.json'):
                if json_file.name == 'relaciones_con_id.json':
                    continue

                try:
                    with open(json_file, 'r', encoding='utf-8') as f:
                        data = json.load(f)

                    texto = data.get('texto_completo', '')
                    if len(texto) < 100:
                        continue

                    id_norma = data.get('id_norma', json_file.stem)
                    textos.append(self._limpiar_texto(texto))
                    ids.append(id_norma)
                    metadatos[id_norma] = {
                        'tipo': data.get('tipo', ''),
                        'numero': data.get('numero', ''),
                        'texto_original': texto,
                    }

                except Exception as e:
                    print(f"Error en {json_file}: {e}")

        print(f"Cargadas {len(textos)} normas")

        # Paso 1: Extraer términos TF-IDF
        print("Extrayendo términos importantes (TF-IDF)...")
        terminos_tfidf = self._extraer_terminos_tfidf(textos, ids)

        # Paso 2: Extraer definiciones por norma
        print("Detectando definiciones...")
        definiciones_por_norma = {}
        for texto, id_norma in zip(textos, ids):
            texto_original = metadatos[id_norma]['texto_original']
            defs = self._extraer_definiciones(texto_original)
            siglas = self._extraer_siglas(texto_original)
            definiciones_por_norma[id_norma] = list(set(defs + siglas))

        # Paso 3: Consolidar todos los conceptos candidatos (normalizado por case)
        print("Consolidando conceptos...")
        todos_conceptos = {}  # lowercase -> forma canónica

        for id_norma, terminos in terminos_tfidf.items():
            for termino, score in terminos[:self.max_conceptos]:
                termino_lower = termino.lower()
                # Preferir forma con mayúscula inicial si es la primera vez
                if termino_lower not in todos_conceptos:
                    todos_conceptos[termino_lower] = termino

        for id_norma, defs in definiciones_por_norma.items():
            for d in defs:
                d_lower = d.lower()
                if d_lower not in todos_conceptos:
                    todos_conceptos[d_lower] = d

        # Convertir a set de formas canónicas
        todos_conceptos_set = set(todos_conceptos.values())

        print(f"Conceptos candidatos: {len(todos_conceptos)}")

        # Paso 4: Calcular coocurrencia
        print("Calculando coocurrencia...")
        coocurrencia = self._calcular_coocurrencia(
            [metadatos[id_]['texto_original'] for id_ in ids],
            ids,
            todos_conceptos
        )

        # Paso 5: Construir objetos Concepto
        print("Construyendo índice de conceptos...")

        for termino in todos_conceptos:
            # Normas donde está definido
            definido_en = [
                id_norma for id_norma, defs in definiciones_por_norma.items()
                if termino in defs or termino.lower() in [d.lower() for d in defs]
            ]

            # Normas donde se usa (coocurrencia)
            usado_en = list(coocurrencia.get(termino, {}).keys())

            # Frecuencia total
            freq = sum(coocurrencia.get(termino, {}).values())

            # Score de importancia (promedio TF-IDF)
            scores = []
            for id_norma, terminos in terminos_tfidf.items():
                for t, s in terminos:
                    if t.lower() == termino.lower():
                        scores.append(s)
            score_imp = np.mean(scores) if scores else 0.0

            # Filtro final de calidad
            termino_lower = termino.lower()
            es_valido = (
                len(termino) >= 3  # Mínimo 3 caracteres
                and termino_lower not in self.STOPWORDS_LEGAL  # No es stopword
                and not termino_lower.isdigit()  # No es número
                and (freq >= self.min_freq or definido_en)  # Frecuencia o definición
            )

            if es_valido:
                self.conceptos[termino] = Concepto(
                    termino=termino,
                    definido_en=definido_en,
                    usado_en=usado_en,
                    frecuencia=freq,
                    score_importancia=float(score_imp)
                )

        # Paso 6: Construir índice por norma
        print("Construyendo índice por norma...")

        for id_norma in ids:
            conceptos_def = definiciones_por_norma.get(id_norma, [])
            conceptos_uso = [
                c for c, data in self.conceptos.items()
                if id_norma in data.usado_en and c not in conceptos_def
            ]

            self.normas[id_norma] = NormaConceptos(
                id_norma=id_norma,
                tipo=metadatos[id_norma]['tipo'],
                numero=metadatos[id_norma]['numero'],
                conceptos_definidos=conceptos_def[:20],
                conceptos_usados=conceptos_uso[:30],
                es_norma_definitoria=len(conceptos_def) >= 5
            )

        print(f"\n✓ Extracción completada:")
        print(f"  - Conceptos extraídos: {len(self.conceptos)}")
        print(f"  - Normas definitorias: {sum(1 for n in self.normas.values() if n.es_norma_definitoria)}")

        return self.conceptos

    def buscar_definicion(self, termino: str) -> List[str]:
        """Encuentra normas que DEFINEN un término."""
        termino_lower = termino.lower()

        for concepto, data in self.conceptos.items():
            if concepto.lower() == termino_lower or termino_lower in concepto.lower():
                if data.definido_en:
                    return data.definido_en

        return []

    def get_boost_para_query(self, query: str) -> Dict[str, float]:
        """
        Calcula boost para normas basado en la query.

        Si la query es "qué es X", da boost a normas que definen X.

        Returns:
            Dict de id_norma -> factor de boost
        """
        boosts = defaultdict(lambda: 1.0)

        # Detectar si es pregunta de definición
        patron_definicion = r'(?:qu[ée] es|definici[oó]n de|significa|qu[ée] significa)\s+["\']?(\w+)'
        match = re.search(patron_definicion, query.lower())

        if match:
            termino = match.group(1)
            normas_def = self.buscar_definicion(termino)
            for id_norma in normas_def:
                boosts[id_norma] = 2.0  # Boost 2x para normas que definen

        # Boost general para normas definitorias si query menciona conceptos
        query_words = set(query.lower().split())
        for concepto, data in self.conceptos.items():
            if concepto.lower() in query.lower():
                for id_norma in data.definido_en:
                    boosts[id_norma] = max(boosts[id_norma], 1.5)

        return dict(boosts)

    def guardar(self, output_dir: Path):
        """Guarda índices de conceptos."""
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

        # Guardar conceptos
        conceptos_dict = {k: asdict(v) for k, v in self.conceptos.items()}
        with open(output_dir / 'conceptos.json', 'w', encoding='utf-8') as f:
            json.dump(conceptos_dict, f, ensure_ascii=False, indent=2)

        # Guardar índice por norma
        normas_dict = {k: asdict(v) for k, v in self.normas.items()}
        with open(output_dir / 'normas_conceptos.json', 'w', encoding='utf-8') as f:
            json.dump(normas_dict, f, ensure_ascii=False, indent=2)

        # Guardar objeto completo para carga rápida
        with open(output_dir / 'concept_index.pkl', 'wb') as f:
            pickle.dump({'conceptos': self.conceptos, 'normas': self.normas}, f)

        print(f"✓ Guardado en {output_dir}")

    @classmethod
    def cargar(cls, index_dir: Path) -> 'ConceptExtractor':
        """Carga índices desde disco."""
        extractor = cls()

        pkl_path = Path(index_dir) / 'concept_index.pkl'
        if pkl_path.exists():
            with open(pkl_path, 'rb') as f:
                data = pickle.load(f)
                extractor.conceptos = data['conceptos']
                extractor.normas = data['normas']
        else:
            # Cargar desde JSON
            with open(Path(index_dir) / 'conceptos.json', 'r') as f:
                conceptos_dict = json.load(f)
                extractor.conceptos = {
                    k: Concepto(**v) for k, v in conceptos_dict.items()
                }

        return extractor


def main():
    """Script para extraer conceptos."""
    import argparse

    parser = argparse.ArgumentParser(description='Extrae conceptos de normas legales')
    parser.add_argument(
        '--input-dir',
        type=Path,
        default=Path(__file__).parent.parent.parent / 'data' / 'normas_completas',
        help='Directorio con normas'
    )
    parser.add_argument(
        '--output-dir',
        type=Path,
        default=Path(__file__).parent.parent.parent / 'data' / 'concept_index',
        help='Directorio de salida'
    )
    parser.add_argument(
        '--min-freq',
        type=int,
        default=2,
        help='Frecuencia mínima de un concepto'
    )

    args = parser.parse_args()

    extractor = ConceptExtractor(min_freq=args.min_freq)
    extractor.extraer_de_normas(args.input_dir)
    extractor.guardar(args.output_dir)

    # Mostrar estadísticas
    print("\n" + "="*60)
    print("TOP 20 CONCEPTOS (por frecuencia)")
    print("="*60)

    top_conceptos = sorted(
        extractor.conceptos.values(),
        key=lambda x: x.frecuencia,
        reverse=True
    )[:20]

    for c in top_conceptos:
        def_str = f"[DEF: {', '.join(c.definido_en[:2])}]" if c.definido_en else ""
        print(f"  {c.termino}: {c.frecuencia} usos {def_str}")

    print("\n" + "="*60)
    print("NORMAS DEFINITORIAS (definen 5+ conceptos)")
    print("="*60)

    for id_norma, norma in extractor.normas.items():
        if norma.es_norma_definitoria:
            print(f"  {norma.tipo} {norma.numero}: {len(norma.conceptos_definidos)} conceptos")
            print(f"    → {', '.join(norma.conceptos_definidos[:5])}...")


if __name__ == '__main__':
    main()
