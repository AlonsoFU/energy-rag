"""
Parser para detectar relaciones entre normas.
Analiza títulos para encontrar referencias como "MODIFICA DECRETO 62".
"""

import re
from typing import List, Tuple, Optional
from dataclasses import dataclass
from enum import Enum


class RelationType(Enum):
    """Tipos de relación detectables."""
    MODIFICA = "MODIFICA"
    DEROGA = "DEROGA"
    SUSTITUYE = "SUSTITUYE"
    REGLAMENTA = "REGLAMENTA"
    AGREGA = "AGREGA"
    COMPLEMENTA = "COMPLEMENTA"


@dataclass
class DetectedRelation:
    """Relación detectada en un título."""
    relation_type: RelationType
    target_tipo: str          # LEY, DECRETO, DFL, etc.
    target_numero: str        # Número de la norma
    target_año: Optional[int] # Año si se menciona
    descripcion: str          # Detalle (ej: "artículo 3")
    match_text: str           # Texto original que matcheó


class RelationshipParser:
    """Parser para detectar relaciones entre normas desde títulos."""

    # Patrones de tipos de norma
    NORM_TYPES = r'(?:LEY|DECRETO|DFL|DL|RESOLUCIÓN|RESOLUCION|AUTO)'

    # Patrones de relación
    PATTERNS = [
        # MODIFICA
        (RelationType.MODIFICA, [
            # "MODIFICA DECRETO N° 62"
            rf'MODIFICA\s+(?:EL\s+)?({NORM_TYPES})\s*(?:N[°º]?\s*)?(\d+)',
            # "MODIFICA EL ARTÍCULO X DEL DECRETO 62"
            rf'MODIFICA\s+(?:EL\s+)?(?:ART[ÍI]CULO\s+[\d\w\-]+\s+)?(?:DEL?\s+)?({NORM_TYPES})\s*(?:N[°º]?\s*)?(\d+)',
            # "MODIFICATORIO DEL DECRETO 62"
            rf'MODIFICATORI[OA]\s+(?:DEL?\s+)?({NORM_TYPES})\s*(?:N[°º]?\s*)?(\d+)',
        ]),

        # DEROGA
        (RelationType.DEROGA, [
            # "DERÓGASE LEY 19.940"
            rf'DER[OÓ]G(?:ASE|A|AN)\s+(?:LA\s+)?({NORM_TYPES})\s*(?:N[°º]?\s*)?([\d\.]+)',
            # "DEROGA DECRETO 62"
            rf'DEROGA\s+(?:EL\s+)?({NORM_TYPES})\s*(?:N[°º]?\s*)?([\d\.]+)',
            # "DEROGATORIO DE LA LEY"
            rf'DEROGATORI[OA]\s+(?:DE\s+)?(?:LA\s+)?({NORM_TYPES})\s*(?:N[°º]?\s*)?([\d\.]+)',
        ]),

        # SUSTITUYE
        (RelationType.SUSTITUYE, [
            # "SUSTITUYE DECRETO 62"
            rf'SUSTITUYE\s+(?:EL\s+)?({NORM_TYPES})\s*(?:N[°º]?\s*)?(\d+)',
            # "SUSTITUYE EL ARTÍCULO X DEL DECRETO 62"
            rf'SUSTITUYE\s+(?:EL\s+)?(?:ART[ÍI]CULO\s+[\d\w\-]+\s+)?(?:DEL?\s+)?({NORM_TYPES})\s*(?:N[°º]?\s*)?(\d+)',
        ]),

        # REGLAMENTA
        (RelationType.REGLAMENTA, [
            # "REGLAMENTO DE LA LEY 20936"
            rf'REGLAMENT[OA]\s+(?:DE\s+)?(?:LA\s+)?({NORM_TYPES})\s*(?:N[°º]?\s*)?([\d\.]+)',
            # "REGLAMENTA LEY 20936"
            rf'REGLAMENTA\s+(?:LA\s+)?({NORM_TYPES})\s*(?:N[°º]?\s*)?([\d\.]+)',
            # "QUE REGLAMENTA"
            rf'QUE\s+REGLAMENTA\s+(?:LA\s+)?({NORM_TYPES})\s*(?:N[°º]?\s*)?([\d\.]+)',
        ]),

        # AGREGA
        (RelationType.AGREGA, [
            # "AGREGA ARTÍCULO AL DECRETO 62"
            rf'AGREGA\s+(?:[\w\s]+\s+)?(?:AL?\s+)?({NORM_TYPES})\s*(?:N[°º]?\s*)?(\d+)',
            # "AGRÉGASE AL DECRETO 62"
            rf'AGR[ÉE]GASE\s+(?:[\w\s]+\s+)?(?:AL?\s+)?({NORM_TYPES})\s*(?:N[°º]?\s*)?(\d+)',
        ]),

        # COMPLEMENTA
        (RelationType.COMPLEMENTA, [
            # "COMPLEMENTA DECRETO 62"
            rf'COMPLEMENTA\s+(?:EL\s+)?({NORM_TYPES})\s*(?:N[°º]?\s*)?(\d+)',
            # "COMPLEMENTARIO DE LEY"
            rf'COMPLEMENTARI[OA]\s+(?:DE\s+)?(?:LA\s+)?({NORM_TYPES})\s*(?:N[°º]?\s*)?([\d\.]+)',
        ]),
    ]

    # Patrón para extraer año
    YEAR_PATTERN = r',?\s*(?:DE\s+)?(?:(?:19|20)\d{2})'

    def __init__(self):
        # Compilar patrones
        self.compiled_patterns = []
        for rel_type, patterns in self.PATTERNS:
            for pattern in patterns:
                self.compiled_patterns.append(
                    (rel_type, re.compile(pattern, re.IGNORECASE))
                )

    def parse_titulo(self, titulo: str) -> List[DetectedRelation]:
        """
        Analizar título y detectar relaciones.

        Args:
            titulo: Título de la norma

        Returns:
            Lista de relaciones detectadas
        """
        relations = []
        titulo_upper = titulo.upper()

        for rel_type, pattern in self.compiled_patterns:
            for match in pattern.finditer(titulo_upper):
                target_tipo = match.group(1).upper()
                target_numero = match.group(2).replace('.', '')  # Quitar puntos

                # Buscar año cercano al match
                año = self._extract_year(titulo_upper, match.end())

                # Extraer descripción (ej: artículo mencionado)
                descripcion = self._extract_descripcion(titulo_upper, match)

                relation = DetectedRelation(
                    relation_type=rel_type,
                    target_tipo=target_tipo,
                    target_numero=target_numero,
                    target_año=año,
                    descripcion=descripcion,
                    match_text=match.group(0)
                )

                # Evitar duplicados
                if not self._is_duplicate(relation, relations):
                    relations.append(relation)

        return relations

    def _extract_year(self, text: str, start_pos: int) -> Optional[int]:
        """Extraer año cercano a la posición."""
        # Buscar en los siguientes 50 caracteres
        search_text = text[start_pos:start_pos + 50]
        match = re.search(r'(?:DE\s+)?((?:19|20)\d{2})', search_text)
        if match:
            return int(match.group(1))
        return None

    def _extract_descripcion(self, text: str, match) -> str:
        """Extraer descripción adicional (artículos, incisos, etc.)."""
        # Buscar menciones de artículos antes del match
        before = text[max(0, match.start() - 100):match.start()]
        art_match = re.search(r'ART[ÍI]CULO\s+([\d\w\-]+)', before)
        if art_match:
            return f"artículo {art_match.group(1)}"
        return ""

    def _is_duplicate(self, new: DetectedRelation, existing: List[DetectedRelation]) -> bool:
        """Verificar si ya existe una relación similar."""
        for rel in existing:
            if (rel.target_tipo == new.target_tipo and
                rel.target_numero == new.target_numero and
                rel.relation_type == new.relation_type):
                return True
        return False

    def analyze_batch(self, titulos: List[str]) -> dict:
        """
        Analizar múltiples títulos y generar estadísticas.

        Returns:
            dict con estadísticas y relaciones
        """
        all_relations = []
        stats = {rt.value: 0 for rt in RelationType}

        for titulo in titulos:
            relations = self.parse_titulo(titulo)
            for rel in relations:
                stats[rel.relation_type.value] += 1
                all_relations.append({
                    'titulo': titulo[:100],
                    'tipo': rel.relation_type.value,
                    'target': f"{rel.target_tipo} {rel.target_numero}",
                    'año': rel.target_año
                })

        return {
            'total_relations': len(all_relations),
            'by_type': stats,
            'relations': all_relations
        }


# Funciones de conveniencia
def detect_relations_in_title(titulo: str) -> List[DetectedRelation]:
    """Detectar relaciones en un título."""
    parser = RelationshipParser()
    return parser.parse_titulo(titulo)


if __name__ == "__main__":
    # Test
    parser = RelationshipParser()

    test_titles = [
        "MODIFICA DECRETO N° 62, DE 2006, REGLAMENTO DE TRANSFERENCIAS DE POTENCIA",
        "DERÓGASE LA LEY 19.940 SOBRE SISTEMA ELÉCTRICO",
        "APRUEBA REGLAMENTO DE LA LEY 20936",
        "SUSTITUYE ARTÍCULO 3 DEL DECRETO 52",
        "AGREGA INCISO AL ARTÍCULO 5 DEL DECRETO 62",
        "MODIFICA RESOLUCIÓN 763 EXENTA DE LA CNE",
        "LEY MARCO DE CIBERSEGURIDAD",  # Sin relación
    ]

    print("=" * 60)
    print("TEST RELATIONSHIP PARSER")
    print("=" * 60)

    for titulo in test_titles:
        print(f"\n📄 {titulo[:70]}...")
        relations = parser.parse_titulo(titulo)
        if relations:
            for rel in relations:
                print(f"   → {rel.relation_type.value}: {rel.target_tipo} {rel.target_numero}")
                if rel.target_año:
                    print(f"      Año: {rel.target_año}")
        else:
            print("   (sin relaciones detectadas)")
