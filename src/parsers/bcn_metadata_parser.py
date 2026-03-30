#!/usr/bin/env python3
"""
Parser para extraer metadatos y relaciones de normas BCN.
Parsea el texto descargado para extraer:
- Metadatos básicos (tipo, número, fecha, organismo)
- Modificaciones (qué decretos modifican esta norma)
- Referencias a otras normas
"""

import re
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, field, asdict
from datetime import datetime


@dataclass
class NormReference:
    """Referencia a otra norma."""
    tipo: str
    numero: str
    año: Optional[int] = None
    organismo: Optional[str] = None
    fecha_do: Optional[str] = None  # Fecha Diario Oficial
    articulo: Optional[str] = None  # Qué artículo modifica
    id_norma: Optional[str] = None  # ID BCN si se conoce


@dataclass
class ParsedNorm:
    """Norma parseada con todos sus metadatos."""
    id_norma: str
    tipo: str
    numero: str
    titulo: str
    fecha_publicacion: Optional[str] = None
    fecha_promulgacion: Optional[str] = None
    organismo: Optional[str] = None
    estado: str = "VIGENTE"

    # Relaciones
    modificada_por: List[NormReference] = field(default_factory=list)
    modifica_a: List[NormReference] = field(default_factory=list)
    deroga_a: List[NormReference] = field(default_factory=list)
    derogada_por: List[NormReference] = field(default_factory=list)
    reglamenta: List[NormReference] = field(default_factory=list)
    referencias: List[NormReference] = field(default_factory=list)

    def to_dict(self) -> dict:
        """Convertir a diccionario serializable."""
        d = asdict(self)
        # Convertir listas de dataclasses a dicts
        for key in ['modificada_por', 'modifica_a', 'deroga_a', 'derogada_por', 'reglamenta', 'referencias']:
            d[key] = [asdict(ref) for ref in getattr(self, key)]
        return d


class BCNMetadataParser:
    """Parser de metadatos de normas BCN."""

    # Patrones para tipos de norma
    TIPO_PATTERNS = [
        (r'\bLEY\s+(?:N[°º]?\s*)?(\d+(?:\.\d+)?)', 'LEY'),
        (r'\bDFL\s+(?:N[°º]?\s*)?(\d+)', 'DFL'),
        (r'\bDL\s+(?:N[°º]?\s*)?(\d+)', 'DL'),
        (r'\bDECRETO\s+(?:SUPREMO\s+)?(?:N[°º]?\s*)?(\d+)', 'DECRETO'),
        (r'\bRESOLUCIÓN\s+(?:N[°º]?\s*)?(\d+)', 'RESOLUCION'),
        (r'\bRESOLUCION\s+(?:N[°º]?\s*)?(\d+)', 'RESOLUCION'),
    ]

    # Patrón para modificaciones inline (formato BCN)
    # Ejemplo: "Decreto 70, ENERGÍA\nArt. primero N° 1\nD.O. 05.06.2024"
    MODIFICACION_PATTERN = re.compile(
        r'(Decreto|Ley|DFL|DL|Resolución)\s+(\d+)(?:\s+EXENTO)?,?\s*'
        r'([A-ZÁÉÍÓÚÑ]+(?:\s+[A-ZÁÉÍÓÚÑ]+)*)\s*\n'  # Organismo
        r'(?:Art\.?\s*([^\n]+)\s*\n)?'  # Artículo (opcional)
        r'D\.O\.\s*(\d{2}\.\d{2}\.\d{4})',  # Fecha DO
        re.IGNORECASE | re.MULTILINE
    )

    # Patrón para referencias en texto
    REFERENCIA_PATTERN = re.compile(
        r'(?:el\s+|la\s+|del\s+|de\s+la\s+)?'
        r'(Ley|Decreto|DFL|DL|Resolución)\s+'
        r'(?:Supremo\s+)?(?:N[°º]?\s*)?'
        r'(\d+(?:\.\d+)?)'
        r'(?:,?\s*(?:de\s+)?(\d{4}))?',
        re.IGNORECASE
    )

    def __init__(self):
        pass

    def parse(self, texto: str, id_norma: str, titulo: str = "") -> ParsedNorm:
        """
        Parsear texto de norma y extraer metadatos.

        Args:
            texto: Texto completo de la norma
            id_norma: ID BCN
            titulo: Título si se conoce

        Returns:
            ParsedNorm con todos los metadatos
        """
        # Extraer tipo y número del título o texto
        tipo, numero = self._extract_tipo_numero(titulo or texto[:500])

        # Extraer fechas
        fecha_pub = self._extract_fecha_publicacion(texto)
        fecha_prom = self._extract_fecha_promulgacion(texto)

        # Extraer organismo
        organismo = self._extract_organismo(texto)

        # Extraer modificaciones (otros decretos que modifican este)
        modificada_por = self._extract_modificaciones(texto)

        # Extraer referencias a otras normas
        referencias = self._extract_referencias(texto)

        # Determinar estado
        estado = self._determinar_estado(texto, modificada_por)

        # Título limpio
        titulo_limpio = self._limpiar_titulo(titulo or self._extract_titulo(texto))

        return ParsedNorm(
            id_norma=id_norma,
            tipo=tipo,
            numero=numero,
            titulo=titulo_limpio,
            fecha_publicacion=fecha_pub,
            fecha_promulgacion=fecha_prom,
            organismo=organismo,
            estado=estado,
            modificada_por=modificada_por,
            referencias=referencias
        )

    def _extract_tipo_numero(self, texto: str) -> Tuple[str, str]:
        """Extraer tipo y número de norma."""
        # Primero buscar en formato "Núm. 62" que es más específico del decreto
        num_match = re.search(r'N[úu]m\.?\s*(\d+)\.?\s*[-–—]?\s*Santiago', texto)
        if num_match:
            return "DECRETO", num_match.group(1)

        # Buscar en las primeras líneas del texto (título)
        primeras_lineas = texto[:500].upper()

        # Patrones específicos para el encabezado
        encabezado_patterns = [
            (r'^.*?(LEY)\s+(?:N[°º]?\s*)?(\d+(?:\.\d+)?)', 'LEY'),
            (r'^.*?(DFL)\s+(?:N[°º]?\s*)?(\d+)', 'DFL'),
            (r'^.*?(DL)\s+(?:N[°º]?\s*)?(\d+)', 'DL'),
            (r'^.*?(DECRETO)\s+(\d+)', 'DECRETO'),
            (r'^.*?(RESOLUCI[ÓO]N)\s+(?:N[°º]?\s*)?(\d+)', 'RESOLUCION'),
        ]

        for pattern, tipo in encabezado_patterns:
            match = re.search(pattern, primeras_lineas, re.MULTILINE)
            if match:
                numero = match.group(2).replace('.', '')
                return tipo, numero

        # Buscar "Núm. X" genérico
        num_match = re.search(r'N[úu]m\.?\s*(\d+)', texto)
        if num_match:
            return "DECRETO", num_match.group(1)

        return "OTRO", ""

    def _extract_fecha_publicacion(self, texto: str) -> Optional[str]:
        """Extraer fecha de publicación."""
        patterns = [
            r'Fecha\s*(?:de\s*)?Publicación[:\s]*(\d{2}[-/]\w{3}[-/]\d{4})',
            r'D\.O\.\s*(\d{2}\.\d{2}\.\d{4})',
            r'Diario\s*Oficial[:\s]*(\d{2}[-/]\w{3}[-/]\d{4})',
        ]
        for pattern in patterns:
            match = re.search(pattern, texto, re.IGNORECASE)
            if match:
                return match.group(1)
        return None

    def _extract_fecha_promulgacion(self, texto: str) -> Optional[str]:
        """Extraer fecha de promulgación."""
        # Buscar "Santiago, 1 de febrero de 2006"
        match = re.search(
            r'Santiago,\s*(\d{1,2})\s*de\s*(\w+)\s*de\s*(\d{4})',
            texto, re.IGNORECASE
        )
        if match:
            dia, mes, año = match.groups()
            return f"{dia} de {mes} de {año}"
        return None

    def _extract_organismo(self, texto: str) -> Optional[str]:
        """Extraer organismo emisor."""
        patterns = [
            r'MINISTERIO\s+DE\s+([A-ZÁÉÍÓÚÑ\s,]+?)(?:\n|;)',
            r'del\s+Ministerio\s+de\s+([A-Za-záéíóúñÁÉÍÓÚÑ\s]+?)(?:,|\.|\n)',
        ]
        for pattern in patterns:
            match = re.search(pattern, texto)
            if match:
                return match.group(1).strip()
        return None

    def _extract_modificaciones(self, texto: str) -> List[NormReference]:
        """Extraer decretos que modifican esta norma."""
        modificaciones = []
        seen = set()

        for match in self.MODIFICACION_PATTERN.finditer(texto):
            tipo = match.group(1).upper()
            numero = match.group(2)
            organismo = match.group(3)
            articulo = match.group(4)
            fecha_do = match.group(5)

            # Evitar duplicados
            key = f"{tipo}_{numero}_{fecha_do}"
            if key in seen:
                continue
            seen.add(key)

            # Extraer año de fecha DO
            año = None
            if fecha_do:
                año_match = re.search(r'(\d{4})', fecha_do)
                if año_match:
                    año = int(año_match.group(1))

            modificaciones.append(NormReference(
                tipo=tipo,
                numero=numero,
                año=año,
                organismo=organismo,
                fecha_do=fecha_do,
                articulo=articulo.strip() if articulo else None
            ))

        return modificaciones

    def _extract_referencias(self, texto: str) -> List[NormReference]:
        """Extraer referencias a otras normas en el texto."""
        referencias = []
        seen = set()

        for match in self.REFERENCIA_PATTERN.finditer(texto):
            tipo = match.group(1).upper()
            numero = match.group(2).replace('.', '')
            año = int(match.group(3)) if match.group(3) else None

            key = f"{tipo}_{numero}"
            if key in seen:
                continue
            seen.add(key)

            referencias.append(NormReference(
                tipo=tipo,
                numero=numero,
                año=año
            ))

        return referencias

    def _determinar_estado(self, texto: str, modificada_por: List[NormReference]) -> str:
        """Determinar estado de la norma."""
        texto_upper = texto.upper()

        if 'DEROGAD' in texto_upper and ('TOTALMENTE' in texto_upper or 'ÍNTEGRAMENTE' in texto_upper):
            return "DEROGADA"

        if modificada_por:
            return "MODIFICADA"

        return "VIGENTE"

    def _extract_titulo(self, texto: str) -> str:
        """Extraer título del texto."""
        lines = texto.split('\n')
        for line in lines[3:10]:  # Buscar en las primeras líneas
            line = line.strip()
            if len(line) > 20 and line.isupper():
                return line
        return ""

    def _limpiar_titulo(self, titulo: str) -> str:
        """Limpiar título."""
        # Quitar prefijos comunes
        titulo = re.sub(r'^(DECRETO|LEY|DFL|DL|RESOLUCIÓN)\s+\d+\s*', '', titulo)
        return titulo.strip()


def parse_norm_file(txt_path: str, id_norma: str) -> ParsedNorm:
    """
    Parsear archivo de texto de norma.

    Args:
        txt_path: Ruta al archivo .txt
        id_norma: ID BCN

    Returns:
        ParsedNorm
    """
    with open(txt_path, 'r', encoding='utf-8') as f:
        texto = f.read()

    parser = BCNMetadataParser()
    return parser.parse(texto, id_norma)


# Test
if __name__ == "__main__":
    import sys
    from pathlib import Path

    # Parsear Decreto 62
    txt_path = Path(__file__).parent.parent.parent / "data" / "textos" / "250604.txt"

    if txt_path.exists():
        print("=" * 60)
        print("PARSEANDO DECRETO 62")
        print("=" * 60)

        norm = parse_norm_file(str(txt_path), "250604")

        print(f"\nTipo: {norm.tipo}")
        print(f"Número: {norm.numero}")
        print(f"Título: {norm.titulo[:80]}...")
        print(f"Organismo: {norm.organismo}")
        print(f"Fecha promulgación: {norm.fecha_promulgacion}")
        print(f"Estado: {norm.estado}")

        print(f"\nModificada por ({len(norm.modificada_por)}):")
        for mod in norm.modificada_por:
            print(f"  - {mod.tipo} {mod.numero} ({mod.año}) - {mod.organismo}")
            if mod.articulo:
                print(f"    Artículo: {mod.articulo}")

        print(f"\nReferencias ({len(norm.referencias)}):")
        for ref in norm.referencias[:10]:
            print(f"  - {ref.tipo} {ref.numero}" + (f" ({ref.año})" if ref.año else ""))
    else:
        print(f"Archivo no encontrado: {txt_path}")
