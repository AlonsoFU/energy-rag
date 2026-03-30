#!/usr/bin/env python3
"""
Parser para extraer estructura jerárquica completa de normas BCN.
Extrae:
- Títulos, Artículos, Incisos
- Modificaciones por artículo (qué decreto modificó qué parte)
- Referencias con contexto (en qué artículo aparece cada referencia)
"""

import re
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, field, asdict
from datetime import datetime


@dataclass
class Modificacion:
    """Una modificación a un artículo específico."""
    tipo: str  # DECRETO, LEY, etc.
    numero: str
    organismo: Optional[str] = None
    articulo_modificador: Optional[str] = None  # Art. primero N° 1
    fecha_do: Optional[str] = None
    id_norma: Optional[str] = None


@dataclass
class Referencia:
    """Referencia a otra norma dentro del texto."""
    tipo: str
    numero: str
    año: Optional[int] = None
    contexto: Optional[str] = None  # Texto donde aparece la referencia
    en_articulo: Optional[str] = None  # En qué artículo de esta norma aparece
    id_norma: Optional[str] = None


@dataclass
class Articulo:
    """Un artículo de la norma con toda su información."""
    numero: str  # "1", "2", "primero", etc.
    texto: str  # Texto limpio (sin anotaciones)
    texto_original: str = ""  # Texto con anotaciones
    modificaciones: List[Modificacion] = field(default_factory=list)
    referencias: List[Referencia] = field(default_factory=list)
    en_titulo: Optional[str] = None  # Título al que pertenece


@dataclass
class Titulo:
    """Un título/capítulo de la norma."""
    numero: str  # "I", "II", "1", etc.
    nombre: str
    articulos: List[str] = field(default_factory=list)  # Lista de números de artículo


@dataclass
class NormaEstructurada:
    """Norma completa con estructura jerárquica."""
    id_norma: str
    tipo: str
    numero: str
    nombre: str
    fecha_publicacion: Optional[str] = None
    fecha_promulgacion: Optional[str] = None
    organismo: Optional[str] = None
    estado: str = "VIGENTE"

    # Estructura jerárquica
    titulos: List[Titulo] = field(default_factory=list)
    articulos: Dict[str, Articulo] = field(default_factory=dict)

    # Relaciones agregadas
    modificada_por: List[Modificacion] = field(default_factory=list)
    todas_referencias: List[Referencia] = field(default_factory=list)

    def to_dict(self) -> dict:
        """Convertir a diccionario serializable."""
        return {
            "id_norma": self.id_norma,
            "tipo": self.tipo,
            "numero": self.numero,
            "nombre": self.nombre,
            "fecha_publicacion": self.fecha_publicacion,
            "fecha_promulgacion": self.fecha_promulgacion,
            "organismo": self.organismo,
            "estado": self.estado,
            "estructura": {
                "titulos": [asdict(t) for t in self.titulos],
                "articulos": {k: asdict(v) for k, v in self.articulos.items()}
            },
            "relaciones": {
                "modificada_por": [asdict(m) for m in self.modificada_por],
                "referencias": [asdict(r) for r in self.todas_referencias]
            }
        }


class NormStructureParser:
    """Parser de estructura jerárquica de normas."""

    # Patrón para títulos
    TITULO_PATTERN = re.compile(
        r'(?:^|\n)\s*T[ÍI]TULO\s+([IVX\d]+)\s*[:\.\-]?\s*([A-ZÁÉÍÓÚÑ\s,]+?)(?=\n|Artículo)',
        re.IGNORECASE | re.MULTILINE
    )

    # Patrón para artículos
    ARTICULO_PATTERN = re.compile(
        r'(?:^|\n)\s*Art[íi]culo\s+(\d+|primero|segundo|tercero|cuarto|quinto|sexto|'
        r'séptimo|octavo|noveno|décimo|único)[°ºª]?\s*[:\.\-]?\s*',
        re.IGNORECASE | re.MULTILINE
    )

    # Patrón para modificaciones inline (formato BCN)
    MODIFICACION_PATTERN = re.compile(
        r'(Decreto|Ley|DFL|DL|Resolución)\s+(\d+)(?:\s+EXENTO)?,?\s*'
        r'([A-ZÁÉÍÓÚÑ]+(?:\s+[A-ZÁÉÍÓÚÑ]+)*)\s*\n'
        r'(?:Art\.?\s*([^\n]+)\s*\n)?'
        r'D\.O\.\s*(\d{2}\.\d{2}\.\d{4})',
        re.IGNORECASE | re.MULTILINE
    )

    # Patrón para referencias a otras normas
    REFERENCIA_PATTERN = re.compile(
        r'(?:el|la|del|de\s+la|al|las)?\s*'
        r'(Ley(?:es)?|Decreto|DFL|DL|Resolución|D\.F\.L\.?|D\.S\.?|'
        r'Decreto\s+(?:Supremo|con\s+Fuerza\s+de\s+Ley))\s+'
        r'(?:N[°º]?\s*)?'
        r'(\d+(?:\.\d+)?)'
        r'(?:[,\s]+(?:de\s+)?(?:\w+\s+de\s+)?(\d{4}))?',
        re.IGNORECASE
    )

    def __init__(self):
        pass

    def parse(self, texto: str, id_norma: str, metadata: dict = None) -> NormaEstructurada:
        """
        Parsear texto completo de norma y extraer estructura.

        Args:
            texto: Texto completo de la norma
            id_norma: ID BCN
            metadata: Metadatos conocidos (tipo, numero, nombre, etc.)

        Returns:
            NormaEstructurada con toda la información
        """
        metadata = metadata or {}

        # Extraer información básica
        tipo = metadata.get('tipo', self._extract_tipo(texto))
        numero = metadata.get('numero', self._extract_numero(texto))
        nombre = metadata.get('nombre', self._extract_nombre(texto))

        # Crear norma
        norma = NormaEstructurada(
            id_norma=id_norma,
            tipo=tipo,
            numero=numero,
            nombre=nombre,
            fecha_publicacion=self._extract_fecha_publicacion(texto),
            fecha_promulgacion=self._extract_fecha_promulgacion(texto),
            organismo=self._extract_organismo(texto)
        )

        # Extraer títulos
        norma.titulos = self._extract_titulos(texto)

        # Extraer artículos con sus modificaciones
        norma.articulos = self._extract_articulos(texto, norma.titulos)

        # Agregar referencias a cada artículo
        self._extract_referencias_por_articulo(norma)

        # Extraer referencias del preámbulo (Vistos, Considerando)
        referencias_preambulo = self._extract_referencias_preambulo(texto)

        # Consolidar modificaciones únicas
        norma.modificada_por = self._consolidar_modificaciones(norma.articulos)

        # Consolidar todas las referencias (artículos + preámbulo)
        norma.todas_referencias = self._consolidar_referencias(norma.articulos, referencias_preambulo)

        # Determinar estado
        norma.estado = self._determinar_estado(norma)

        return norma

    def _extract_tipo(self, texto: str) -> str:
        """Extraer tipo de norma."""
        texto_upper = texto[:500].upper()
        if 'LEY' in texto_upper:
            return 'LEY'
        elif 'D.F.L.' in texto_upper or 'DFL' in texto_upper:
            return 'DFL'
        elif 'D.L.' in texto_upper or 'DECRETO LEY' in texto_upper:
            return 'DL'
        elif 'RESOLUCIÓN' in texto_upper or 'RESOLUCION' in texto_upper:
            return 'RESOLUCION'
        elif 'DECRETO' in texto_upper:
            return 'DECRETO'
        return 'OTRO'

    def _extract_numero(self, texto: str) -> str:
        """Extraer número de norma."""
        # Buscar "Núm. XX" que es el formato oficial
        match = re.search(r'N[úu]m\.?\s*(\d+)', texto)
        if match:
            return match.group(1)

        # Buscar en título
        match = re.search(r'(?:LEY|DECRETO|DFL|DL|RESOLUCIÓN)\s+(?:N[°º]?\s*)?(\d+)', texto[:500], re.IGNORECASE)
        if match:
            return match.group(1)

        return ""

    def _extract_nombre(self, texto: str) -> str:
        """Extraer nombre/título de la norma."""
        # Buscar líneas en mayúsculas al inicio
        lines = texto.split('\n')
        for line in lines[2:15]:
            line = line.strip()
            if len(line) > 20 and line.isupper() and not line.startswith('MINISTERIO'):
                return line
        return ""

    def _extract_fecha_publicacion(self, texto: str) -> Optional[str]:
        """Extraer fecha de publicación."""
        match = re.search(r'D\.O\.\s*(\d{2}\.\d{2}\.\d{4})', texto)
        if match:
            return match.group(1)
        return None

    def _extract_fecha_promulgacion(self, texto: str) -> Optional[str]:
        """Extraer fecha de promulgación."""
        match = re.search(
            r'Santiago,\s*(\d{1,2})\s*de\s*(\w+)\s*de\s*(\d{4})',
            texto, re.IGNORECASE
        )
        if match:
            return f"{match.group(1)} de {match.group(2)} de {match.group(3)}"
        return None

    def _extract_organismo(self, texto: str) -> Optional[str]:
        """Extraer organismo emisor."""
        match = re.search(r'MINISTERIO\s+DE\s+([A-ZÁÉÍÓÚÑ\s,]+?)(?:\n|;)', texto)
        if match:
            return match.group(1).strip()
        return None

    def _extract_titulos(self, texto: str) -> List[Titulo]:
        """Extraer títulos/capítulos."""
        titulos = []
        for match in self.TITULO_PATTERN.finditer(texto):
            titulos.append(Titulo(
                numero=match.group(1),
                nombre=match.group(2).strip()
            ))
        return titulos

    def _extract_articulos(self, texto: str, titulos: List[Titulo]) -> Dict[str, Articulo]:
        """Extraer artículos con sus modificaciones."""
        articulos = {}

        # Encontrar posiciones de todos los artículos
        matches = list(self.ARTICULO_PATTERN.finditer(texto))

        for i, match in enumerate(matches):
            num_articulo = match.group(1).lower()

            # Determinar fin del artículo
            start = match.end()
            end = matches[i + 1].start() if i + 1 < len(matches) else len(texto)

            texto_articulo = texto[start:end].strip()

            # Extraer modificaciones dentro de este artículo
            modificaciones = self._extract_modificaciones_de_texto(texto_articulo)

            # Determinar a qué título pertenece
            en_titulo = self._find_titulo_for_position(match.start(), texto, titulos)

            articulos[num_articulo] = Articulo(
                numero=num_articulo,
                texto=self._limpiar_texto_articulo(texto_articulo),
                texto_original=texto_articulo,
                modificaciones=modificaciones,
                en_titulo=en_titulo
            )

            # Agregar artículo al título correspondiente
            for titulo in titulos:
                if titulo.numero == en_titulo:
                    titulo.articulos.append(num_articulo)
                    break

        return articulos

    def _extract_modificaciones_de_texto(self, texto: str) -> List[Modificacion]:
        """Extraer modificaciones inline de un fragmento de texto."""
        modificaciones = []
        seen = set()

        for match in self.MODIFICACION_PATTERN.finditer(texto):
            tipo = match.group(1).upper()
            numero = match.group(2)
            organismo = match.group(3)
            articulo = match.group(4)
            fecha_do = match.group(5)

            key = f"{tipo}_{numero}_{fecha_do}"
            if key in seen:
                continue
            seen.add(key)

            modificaciones.append(Modificacion(
                tipo=tipo,
                numero=numero,
                organismo=organismo,
                articulo_modificador=articulo.strip() if articulo else None,
                fecha_do=fecha_do
            ))

        return modificaciones

    def _extract_referencias_por_articulo(self, norma: NormaEstructurada):
        """Extraer referencias a otras normas dentro de cada artículo."""
        for num, articulo in norma.articulos.items():
            seen = set()
            # Usar texto original para buscar referencias
            texto_buscar = articulo.texto_original or articulo.texto

            for match in self.REFERENCIA_PATTERN.finditer(texto_buscar):
                tipo_raw = match.group(1).upper()
                numero = match.group(2).replace('.', '')
                año = int(match.group(3)) if match.group(3) else None

                # Normalizar tipo
                tipo = tipo_raw
                if 'D.F.L' in tipo_raw or 'DFL' in tipo_raw or 'FUERZA DE LEY' in tipo_raw:
                    tipo = 'DFL'
                elif 'D.S' in tipo_raw or 'SUPREMO' in tipo_raw:
                    tipo = 'DECRETO'
                elif 'D.L' in tipo_raw:
                    tipo = 'DL'
                elif 'LEY' in tipo_raw:
                    tipo = 'LEY'

                key = f"{tipo}_{numero}"
                if key in seen:
                    continue
                seen.add(key)

                # Extraer contexto (texto alrededor de la referencia)
                start = max(0, match.start() - 50)
                end = min(len(texto_buscar), match.end() + 50)
                contexto = texto_buscar[start:end].strip()

                articulo.referencias.append(Referencia(
                    tipo=tipo,
                    numero=numero,
                    año=año,
                    contexto=contexto,
                    en_articulo=num
                ))

    def _extract_referencias_preambulo(self, texto: str) -> List[Referencia]:
        """Extraer referencias del preámbulo (Vistos, Considerando)."""
        referencias = []
        seen = set()

        # Encontrar el preámbulo (antes del primer artículo)
        match = self.ARTICULO_PATTERN.search(texto)
        preambulo = texto[:match.start()] if match else texto[:2000]

        for match in self.REFERENCIA_PATTERN.finditer(preambulo):
            tipo_raw = match.group(1).upper()
            numero = match.group(2).replace('.', '')
            año = int(match.group(3)) if match.group(3) else None

            # Normalizar tipo
            tipo = tipo_raw
            if 'D.F.L' in tipo_raw or 'DFL' in tipo_raw or 'FUERZA DE LEY' in tipo_raw:
                tipo = 'DFL'
            elif 'D.S' in tipo_raw or 'SUPREMO' in tipo_raw:
                tipo = 'DECRETO'
            elif 'D.L' in tipo_raw:
                tipo = 'DL'
            elif 'LEY' in tipo_raw:
                tipo = 'LEY'

            key = f"{tipo}_{numero}"
            if key in seen:
                continue
            seen.add(key)

            # Extraer contexto
            start = max(0, match.start() - 50)
            end = min(len(preambulo), match.end() + 50)
            contexto = preambulo[start:end].strip()

            referencias.append(Referencia(
                tipo=tipo,
                numero=numero,
                año=año,
                contexto=contexto,
                en_articulo="preámbulo"
            ))

        return referencias

    def _find_titulo_for_position(self, pos: int, texto: str, titulos: List[Titulo]) -> Optional[str]:
        """Encontrar a qué título pertenece una posición en el texto."""
        titulo_actual = None

        for match in self.TITULO_PATTERN.finditer(texto):
            if match.start() < pos:
                titulo_actual = match.group(1)
            else:
                break

        return titulo_actual

    def _limpiar_texto_articulo(self, texto: str) -> str:
        """Limpiar texto de artículo removiendo anotaciones de modificación."""
        # Remover anotaciones de modificación para tener texto limpio
        texto_limpio = self.MODIFICACION_PATTERN.sub('', texto)
        # Limpiar espacios múltiples
        texto_limpio = re.sub(r'\n\s*\n', '\n\n', texto_limpio)
        texto_limpio = re.sub(r' +', ' ', texto_limpio)
        return texto_limpio.strip()

    def _consolidar_modificaciones(self, articulos: Dict[str, Articulo]) -> List[Modificacion]:
        """Consolidar modificaciones únicas de todos los artículos."""
        todas = []
        seen = set()

        for articulo in articulos.values():
            for mod in articulo.modificaciones:
                key = f"{mod.tipo}_{mod.numero}_{mod.fecha_do}"
                if key not in seen:
                    seen.add(key)
                    todas.append(mod)

        return todas

    def _consolidar_referencias(self, articulos: Dict[str, Articulo], refs_preambulo: List[Referencia] = None) -> List[Referencia]:
        """Consolidar referencias únicas de todos los artículos y preámbulo."""
        todas = []
        seen = set()

        # Referencias del preámbulo primero
        if refs_preambulo:
            for ref in refs_preambulo:
                key = f"{ref.tipo}_{ref.numero}"
                if key not in seen:
                    seen.add(key)
                    todas.append(ref)

        # Referencias de artículos
        for articulo in articulos.values():
            for ref in articulo.referencias:
                key = f"{ref.tipo}_{ref.numero}"
                if key not in seen:
                    seen.add(key)
                    todas.append(ref)

        return todas

    def _determinar_estado(self, norma: NormaEstructurada) -> str:
        """Determinar estado de la norma."""
        if norma.modificada_por:
            return "MODIFICADA"
        return "VIGENTE"


def parse_norm_structure(txt_path: str, id_norma: str, metadata: dict = None) -> NormaEstructurada:
    """
    Parsear archivo de texto y extraer estructura completa.

    Args:
        txt_path: Ruta al archivo .txt
        id_norma: ID BCN
        metadata: Metadatos conocidos

    Returns:
        NormaEstructurada
    """
    with open(txt_path, 'r', encoding='utf-8') as f:
        texto = f.read()

    parser = NormStructureParser()
    return parser.parse(texto, id_norma, metadata)


# Test
if __name__ == "__main__":
    import json
    from pathlib import Path

    txt_path = Path(__file__).parent.parent.parent / "data" / "textos" / "250604.txt"

    if txt_path.exists():
        print("=" * 70)
        print("PARSEANDO ESTRUCTURA DE DECRETO 62")
        print("=" * 70)

        norma = parse_norm_structure(
            str(txt_path),
            "250604",
            {"tipo": "DECRETO", "numero": "62", "nombre": "Transferencias de Potencia"}
        )

        print(f"\nTipo: {norma.tipo} {norma.numero}")
        print(f"Nombre: {norma.nombre}")
        print(f"Estado: {norma.estado}")

        print(f"\n--- TÍTULOS ({len(norma.titulos)}) ---")
        for titulo in norma.titulos:
            print(f"  Título {titulo.numero}: {titulo.nombre}")
            print(f"    Artículos: {titulo.articulos}")

        print(f"\n--- ARTÍCULOS ({len(norma.articulos)}) ---")
        for num, art in list(norma.articulos.items())[:5]:
            print(f"\n  Artículo {num}:")
            print(f"    Texto: {art.texto[:100]}...")
            if art.modificaciones:
                print(f"    Modificaciones: {len(art.modificaciones)}")
                for mod in art.modificaciones:
                    print(f"      - {mod.tipo} {mod.numero} ({mod.fecha_do})")
            if art.referencias:
                print(f"    Referencias: {len(art.referencias)}")
                for ref in art.referencias[:3]:
                    print(f"      - {ref.tipo} {ref.numero}")

        print(f"\n--- MODIFICACIONES ÚNICAS ({len(norma.modificada_por)}) ---")
        for mod in norma.modificada_por:
            print(f"  {mod.tipo} {mod.numero} - {mod.organismo} - D.O. {mod.fecha_do}")

        print(f"\n--- REFERENCIAS ÚNICAS ({len(norma.todas_referencias)}) ---")
        for ref in norma.todas_referencias[:10]:
            print(f"  {ref.tipo} {ref.numero}" + (f" ({ref.año})" if ref.año else ""))
            print(f"    En artículo: {ref.en_articulo}")
    else:
        print(f"Archivo no encontrado: {txt_path}")
