"""
Construye un grafo de relaciones entre normas legales.

3 capas:
1. Definiciones: conceptos definidos en cada norma (regex "se entenderá por")
2. Referencias cruzadas: norma A menciona norma B (regex "D.S. N°13T", "Ley 20.936")
3. Alias: nombres informales → norma formal (config/alias_normas.json)

Usa NetworkX. Persiste como JSON.
"""

import json
import re
import pickle
from pathlib import Path
from collections import defaultdict
from typing import Dict, List, Tuple, Optional

try:
    import networkx as nx
except ImportError:
    print("Instalando networkx...")
    import subprocess
    subprocess.run(["pip", "install", "networkx", "-q"])
    import networkx as nx


class NormaGraphBuilder:
    """Construye grafo de normas con definiciones, referencias y alias."""

    # Patrones para detectar referencias formales a otras normas
    PATRONES_REF_FORMAL = [
        # D.S. N°13T, DS 13T, D.S. Nº 13T
        (r'[Dd]\.?\s*[Ss]\.?\s*(?:N[°ºo]?\s*)?(\d{1,4}[A-Z]?)', 'DECRETO'),
        # Decreto Supremo N°13, Decreto N°13T
        (r'[Dd]ecreto\s+(?:[Ss]upremo\s+)?(?:N[°ºo]?\s*)?(\d{1,4}[A-Z]?)', 'DECRETO'),
        # Ley N°20.936, Ley 20936, Ley Nº 20.936
        (r'[Ll]ey\s+(?:N[°ºo]?\s*)?(\d{2,5}\.?\d*)', 'LEY'),
        # DFL N°4, DFL 4
        (r'[Dd]\.?\s*[Ff]\.?\s*[Ll]\.?\s*(?:N[°ºo]?\s*)?(\d{1,4})', 'DFL'),
        # Resolución Exenta N°237
        (r'[Rr]esoluci[óo]n\s+(?:[Ee]xenta\s+)?(?:N[°ºo]?\s*)?(\d{1,4})', 'RESOLUCIÓN'),
    ]

    # Patrones para extraer definiciones (acepta mayúscula y minúscula)
    PATRONES_DEFINICION = [
        # "se entenderá por X a la persona..."
        r'[Ss]e\s+entender[áa]\s+por\s+["\']?([A-Za-záéíóúñÁÉÍÓÚÑ][A-Za-záéíóúñÁÉÍÓÚÑ\s]{2,60}?)\s+(?:a\s+|al\s+|el\s+|la\s+|los\s+|las\s+|un\s+|una\s+|cualquier\s+)',
        # "se entenderá por X," o "se entenderá por X:"
        r'[Ss]e\s+entender[áa]\s+por\s+["\']?([A-Za-záéíóúñÁÉÍÓÚÑ][A-Za-záéíóúñÁÉÍÓÚÑ\s]{2,60}?)["\']?\s*[,:]',
        # "se entiende por X"
        r'[Ss]e\s+entiende\s+por\s+["\']?([A-Za-záéíóúñÁÉÍÓÚÑ][A-Za-záéíóúñÁÉÍÓÚÑ\s]{2,60}?)["\']?\s*[,:]',
        # "para efectos de este decreto, X significa..."
        r'[Pp]ara\s+(?:los\s+)?efectos\s+de[^,:.]{0,40}[,:]\s*["\']?([A-Za-záéíóúñÁÉÍÓÚÑ][A-Za-záéíóúñÁÉÍÓÚÑ\s]{2,60}?)["\']?\s*[,:]',
        # "X: significa..." o "X: es..."
        r'([A-ZÁÉÍÓÚÑ][A-Za-záéíóúñÁÉÍÓÚÑ\s]{2,40})\s*[,:]\s*(?:significa|corresponde\s+a|se\s+define\s+como)',
        # Siglas técnicas: "VATTn,k : Valor...", "CDEC : Centro...", "PEAT : Peaje..."
        r'\b([A-Z]{2,10})[a-z,\d\s]{0,10}:\s*[A-Z][a-záéíóúñ]',
        # Siglas con puntos: "C.O.M.A.: Costo...", "A.V.I.: Anualidad...", "V.A.T.T.: Valor..."
        r'\b((?:[A-Z]\.){2,10}[A-Z]\.?)\s*:\s*[A-Z][a-záéíóúñ]',
    ]

    # Patrones para alias informales
    PATRONES_ALIAS = [
        r'(?:el|la|del|al)\s+(reglamento\s+(?:de|del|sobre)\s+[a-záéíóúñ\s]{3,50})',
        r'(?:el|la|del|al)\s+(ley\s+(?:de|del|sobre)\s+[a-záéíóúñ\s]{3,50})',
        r'(?:el|la|del|al)\s+(norma\s+técnica\s+(?:de|del|sobre)\s+[a-záéíóúñ\s]{3,50})',
        r'(ley\s+general\s+de\s+servicios\s+eléctricos)',
    ]

    def __init__(self, normas_dir: Path, config_dir: Path):
        self.normas_dir = Path(normas_dir)
        self.config_dir = Path(config_dir)
        self.G = nx.DiGraph()
        self.normas_data = {}  # id_norma -> metadata
        self.alias_map = {}   # alias texto -> id_norma

    @staticmethod
    def _extraer_año(texto: str, titulo: str) -> str:
        """Extrae año de promulgación del texto o título."""
        # Patrón: "Santiago, DD de MES de YYYY"
        m = re.search(r'Santiago,\s+\d+\s+de\s+\w+\s+de\s+(\d{4})', texto[:1000])
        if m:
            return m.group(1)
        # Fallback: año en título (ej: "DE 2019")
        m = re.search(r'\b((?:19|20)\d{2})\b', titulo)
        if m:
            return m.group(1)
        return ''

    @staticmethod
    def _clasificar_norma(titulo: str) -> str:
        """Clasifica si es reglamento base o decreto derivado.

        Solo clasifica como reglamento_base si 'APRUEBA REGLAMENTO' aparece
        en la parte operativa del título (primeros 80 chars después del tipo/número),
        no en una referencia a otra norma.
        """
        # Limpiar títulos con duplicados de scraping (ej: "DECRETO 13DECRETO 13 T FIJA...")
        t = re.sub(r'^[A-Z]+\s+\d+\s*', '', titulo.upper(), count=1).strip()
        # Clasificar por la acción principal (primera encontrada)
        if re.match(r'(?:T\s+)?APRUEBA\s+REGLAMENTO', t):
            return 'reglamento_base'
        if re.match(r'(?:T\s+)?FIJA\b', t):
            return 'fija_valores'
        if re.match(r'(?:T\s+)?MODIFICA\b', t):
            return 'modifica'
        if re.match(r'(?:T\s+)?DEROGA\b', t):
            return 'deroga'
        # Fallback: buscar en primeros 80 chars
        t80 = t[:80]
        if 'APRUEBA REGLAMENTO' in t80:
            return 'reglamento_base'
        if 'FIJA' in t80:
            return 'fija_valores'
        if 'MODIFICA' in t80:
            return 'modifica'
        return ''

    def _cargar_normas(self):
        """Carga todas las normas."""
        for subdir in self.normas_dir.iterdir():
            if not subdir.is_dir():
                continue
            for jf in subdir.glob("*.json"):
                if jf.name == "relaciones_con_id.json":
                    continue
                try:
                    with open(jf, 'r', encoding='utf-8') as f:
                        data = json.load(f)
                    id_norma = data.get('id_norma', '')
                    if not id_norma:
                        continue
                    titulo = data.get('titulo', '')
                    texto = data.get('texto_completo', '')
                    self.normas_data[id_norma] = {
                        'tipo': data.get('tipo', ''),
                        'numero': data.get('numero', ''),
                        'titulo': titulo,
                        'texto': texto,
                        'año': self._extraer_año(texto, titulo),
                        'clase': self._clasificar_norma(titulo),
                    }
                except Exception:
                    continue

        print(f"Cargadas {len(self.normas_data)} normas")

    def _cargar_alias(self):
        """Carga alias desde config/alias_normas.json."""
        alias_path = self.config_dir / 'alias_normas.json'
        if not alias_path.exists():
            print("No se encontró config/alias_normas.json")
            return

        with open(alias_path, 'r', encoding='utf-8') as f:
            config = json.load(f)

        confirmados = config.get('confirmados', {})
        for alias_texto, id_norma in confirmados.items():
            self.alias_map[alias_texto.lower()] = id_norma

        # Cargar conceptos base (para normas con texto incompleto)
        self.conceptos_base = config.get('conceptos_base', {})

        print(f"Cargados {len(self.alias_map)} alias confirmados")
        if self.conceptos_base:
            print(f"Cargados {len(self.conceptos_base)} normas con conceptos base manuales")

    def _build_indice_normas(self) -> Dict[str, str]:
        """
        Construye índice tipo+numero -> id_norma para resolver referencias formales.
        Ej: ("DECRETO", "13") -> "1215040"
        """
        indice = {}
        for id_norma, data in self.normas_data.items():
            tipo = data['tipo'].upper().strip()
            numero = str(data['numero']).strip()
            if tipo and numero:
                # Clave exacta
                indice[(tipo, numero)] = id_norma
                # Sin puntos (20.936 -> 20936)
                numero_limpio = numero.replace('.', '')
                indice[(tipo, numero_limpio)] = id_norma
        return indice

    def _agregar_nodos_normas(self):
        """Agrega todas las normas como nodos del grafo."""
        for id_norma, data in self.normas_data.items():
            self.G.add_node(
                id_norma,
                tipo_nodo='norma',
                tipo=data['tipo'],
                numero=data['numero'],
                titulo=data['titulo'][:100],
                año=data.get('año', ''),
                clase=data.get('clase', ''),
            )

    def _encontrar_seccion_definiciones(self, texto: str) -> str:
        """Extrae solo la sección de definiciones/glosario de una norma.

        Busca el inicio (Capítulo/Artículo de Definiciones) y el fin
        (siguiente Capítulo/Título). Si no encuentra sección explícita,
        retorna string vacío.
        """
        # Patrones de inicio de sección de definiciones
        inicios = [
            r'(?:Capítulo|Título)\s+\d+[°º]?\s*[-.:]\s*(?:De\s+las\s+)?[Dd]efiniciones',
            r'(?:Artículo|Art\.?)\s+\d+[°º]?\s*[-.:]\s*(?:De\s+las\s+)?[Dd]efiniciones',
            r'[Dd]efiniciones\s*\n',
            r'[Pp]ara\s+(?:los\s+)?efectos\s+de(?:l\s+presente|\s+la\s+aplicación\s+de\s+las\s+disposiciones)',
        ]
        for pat in inicios:
            m = re.search(pat, texto)
            if m:
                inicio = m.start()
                # Buscar fin: siguiente Capítulo/Título
                fin_pat = r'(?:Capítulo|Título)\s+\d+[°º]?\s*[-.:]\s*[A-ZÁÉÍÓÚÑ]'
                m_fin = re.search(fin_pat, texto[m.end():])
                if m_fin:
                    return texto[inicio:m.end() + m_fin.start()]
                # Sin fin explícito, tomar máximo 15000 chars
                return texto[inicio:inicio + 15000]
        return ''

    def _extraer_definiciones(self):
        """Capa 1: extrae conceptos SOLO de glosarios de normas base.

        Solo procesa normas que:
        1. Tienen sección explícita de Definiciones/Glosario
        2. Son reglamentos base (APRUEBA REGLAMENTO) o tienen glosario técnico
        """
        total_defs = 0
        normas_con_glosario = []

        for id_norma, data in self.normas_data.items():
            texto = data['texto']
            if len(texto) < 500:
                continue

            # Buscar sección de definiciones
            seccion = self._encontrar_seccion_definiciones(texto)
            if not seccion:
                continue

            normas_con_glosario.append(f"{data['tipo']} {data['numero']}")

            # Extraer definiciones SOLO de la sección de glosario
            for patron in self.PATRONES_DEFINICION:
                matches = re.findall(patron, seccion)
                for match in matches:
                    termino = self._limpiar_termino(match)
                    if not termino:
                        continue

                    concepto_id, termino_normalizado, variantes = self._normalizar_concepto(termino)

                    if not self.G.has_node(concepto_id):
                        self.G.add_node(
                            concepto_id,
                            tipo_nodo='concepto',
                            termino=termino_normalizado,
                            variantes=variantes,
                        )

                    self.G.add_edge(id_norma, concepto_id, relacion='define')
                    total_defs += 1

        print(f"Normas con glosario: {len(normas_con_glosario)}")
        for n in normas_con_glosario:
            print(f"  - {n}")
        print(f"Definiciones extraídas: {total_defs}")

    def _limpiar_termino(self, match: str) -> str:
        """Limpia y valida un término extraído."""
        termino = match.strip().rstrip('.,;: ')
        termino = re.sub(r'\s+', ' ', termino)
        if len(termino) < 2 or len(termino) > 60:
            return ''

        t_lower = termino.lower()

        # Filtrar stopwords puros
        stopwords = {'el', 'la', 'los', 'las', 'de', 'del', 'en', 'un', 'una',
                     'que', 'por', 'para', 'con', 'se', 'su', 'sus', 'al', 'este',
                     'esta', 'ese', 'esa', 'todo', 'toda', 'otro', 'otra'}
        palabras_utiles = [p for p in t_lower.split() if p not in stopwords and len(p) > 2]
        if len(palabras_utiles) < 1:
            return ''

        # Excluir ruido
        frases_excluir = [
            'se entenderá por', 'se entiende por', 'para efectos',
            'para los efectos', 'presente decreto', 'presente ley',
            'presente reglamento', 'presente resolución',
        ]
        palabras_excluir = {
            'decreto', 'vistos', 'visto', 'resumen', 'materias',
            'considerando', 'donde', 'nota', 'loading', 'escuchar',
            'versiones', 'ocultar', 'notas', 'santiago', 'artículo',
            'decreto ley', 'superintendencia', 'ministerio',
        }
        if any(f in t_lower for f in frases_excluir):
            return ''
        if t_lower.strip() in palabras_excluir:
            return ''

        # Excluir frases largas con verbos (no son conceptos)
        verbos_ruido = ['deberá', 'podrá', 'tendrá', 'será', 'puede', 'debe',
                        'señalado', 'mencionado', 'referido', 'establecido',
                        'sujetarse', 'presentará', 'cumplir']
        if any(v in t_lower for v in verbos_ruido):
            return ''

        # Si tiene más de 5 palabras, probablemente es una frase, no un concepto
        if len(t_lower.split()) > 5:
            return ''

        return termino

    def _normalizar_concepto(self, termino: str):
        """Normaliza un término y retorna (concepto_id, normalizado, variantes)."""
        sigla_sin_puntos = re.sub(r'\.', '', termino)
        if sigla_sin_puntos.isupper() and len(sigla_sin_puntos) >= 2:
            termino_normalizado = sigla_sin_puntos
        else:
            termino_normalizado = termino

        concepto_id = f"concepto:{termino_normalizado.lower()}"
        variantes = list(set([
            termino.lower(),
            termino_normalizado.lower(),
            sigla_sin_puntos.lower(),
        ]))
        return concepto_id, termino_normalizado, variantes

    def _extraer_referencias_formales(self):
        """Capa 2: detecta referencias cruzadas entre normas (D.S. N°X, Ley X)."""
        indice = self._build_indice_normas()
        total_refs = 0

        for id_norma, data in self.normas_data.items():
            texto = data['texto']
            if len(texto) < 100:
                continue

            refs_encontradas = set()

            for patron, tipo_norma in self.PATRONES_REF_FORMAL:
                matches = re.findall(patron, texto)
                for numero in matches:
                    numero_limpio = numero.replace('.', '').strip()
                    # Buscar en el índice
                    id_ref = None
                    for tipo_buscar in [tipo_norma, 'DECRETO', 'LEY', 'DFL', 'RESOLUCIÓN']:
                        clave = (tipo_buscar, numero_limpio)
                        if clave in indice:
                            id_ref = indice[clave]
                            break

                    if id_ref and id_ref != id_norma and id_ref not in refs_encontradas:
                        self.G.add_edge(id_norma, id_ref, relacion='referencia')
                        refs_encontradas.add(id_ref)
                        total_refs += 1

        print(f"Referencias cruzadas: {total_refs}")

    def _extraer_referencias_alias(self):
        """Capa 3: detecta referencias informales usando alias."""
        if not self.alias_map:
            return

        total_alias = 0

        for id_norma, data in self.normas_data.items():
            texto_lower = data['texto'].lower()
            if len(texto_lower) < 100:
                continue

            for alias_texto, id_ref in self.alias_map.items():
                if alias_texto in texto_lower and id_ref != id_norma:
                    if id_ref in self.normas_data:
                        if not self.G.has_edge(id_norma, id_ref):
                            self.G.add_edge(id_norma, id_ref, relacion='alias')
                            total_alias += 1

        print(f"Referencias por alias: {total_alias}")

    def _inyectar_conceptos_base(self):
        """Inyecta conceptos desde config para normas con texto incompleto."""
        total = 0
        for id_norma, info in self.conceptos_base.items():
            conceptos = info.get('conceptos', [])
            for concepto in conceptos:
                concepto_upper = concepto.upper()
                concepto_norm = re.sub(r'\.', '', concepto_upper)
                # Buscar si ya existe nodo concepto
                nodo_concepto = None
                for node, d in self.G.nodes(data=True):
                    if d.get('tipo_nodo') != 'concepto':
                        continue
                    if d.get('termino', '').upper() == concepto_norm:
                        nodo_concepto = node
                        break
                    variantes = [v.upper() for v in d.get('variantes', [])]
                    if concepto_norm in variantes or concepto_upper in variantes:
                        nodo_concepto = node
                        break

                if nodo_concepto is None:
                    # Crear nodo concepto nuevo
                    nodo_concepto = f"concepto_{concepto_norm.lower()}"
                    self.G.add_node(
                        nodo_concepto,
                        tipo_nodo='concepto',
                        termino=concepto_norm,
                        variantes=[concepto.lower(), concepto_norm.lower()],
                    )

                # Agregar arista define si no existe
                if id_norma in self.G and not self.G.has_edge(id_norma, nodo_concepto):
                    self.G.add_edge(id_norma, nodo_concepto, relacion='define', fuente='config_manual')
                    total += 1

        print(f"Conceptos base inyectados: {total}")

    def build(self) -> nx.DiGraph:
        """Construye el grafo completo."""
        print("="*60)
        print("CONSTRUYENDO GRAFO DE NORMAS")
        print("="*60)

        self._cargar_normas()
        self._cargar_alias()
        self._agregar_nodos_normas()

        print("\nCapa 1: Definiciones...")
        self._extraer_definiciones()

        print("\nCapa 2: Referencias formales...")
        self._extraer_referencias_formales()

        print("\nCapa 3: Referencias por alias...")
        self._extraer_referencias_alias()

        print("\nCapa 4: Conceptos base manuales...")
        self._inyectar_conceptos_base()

        # Estadísticas
        n_normas = sum(1 for _, d in self.G.nodes(data=True) if d.get('tipo_nodo') == 'norma')
        n_conceptos = sum(1 for _, d in self.G.nodes(data=True) if d.get('tipo_nodo') == 'concepto')
        n_aristas = self.G.number_of_edges()

        print(f"\n{'='*60}")
        print(f"GRAFO CONSTRUIDO:")
        print(f"  Nodos norma:    {n_normas}")
        print(f"  Nodos concepto: {n_conceptos}")
        print(f"  Aristas total:  {n_aristas}")

        # Top normas más referenciadas
        print(f"\nTOP 10 NORMAS MÁS REFERENCIADAS:")
        in_degree = {}
        for node, d in self.G.nodes(data=True):
            if d.get('tipo_nodo') == 'norma':
                refs = sum(1 for _, _, ed in self.G.in_edges(node, data=True)
                           if ed.get('relacion') in ('referencia', 'alias'))
                if refs > 0:
                    in_degree[node] = refs

        for node, refs in sorted(in_degree.items(), key=lambda x: -x[1])[:10]:
            d = self.G.nodes[node]
            print(f"  [{refs:3d} refs] {d.get('tipo','')} {d.get('numero','')} - {d.get('titulo','')[:70]}")

        # Top conceptos más definidos
        print(f"\nTOP 10 CONCEPTOS MÁS DEFINIDOS (en más normas):")
        concepto_defs = {}
        for node, d in self.G.nodes(data=True):
            if d.get('tipo_nodo') == 'concepto':
                n_defs = self.G.in_degree(node)
                if n_defs > 1:
                    concepto_defs[node] = n_defs

        for node, n_defs in sorted(concepto_defs.items(), key=lambda x: -x[1])[:10]:
            termino = self.G.nodes[node].get('termino', node)
            # Mostrar en qué normas
            normas_def = [self.G.nodes[n].get('tipo','') + ' ' + str(self.G.nodes[n].get('numero',''))
                         for n in self.G.predecessors(node)]
            print(f"  [{n_defs} defs] \"{termino}\" ← {', '.join(normas_def[:4])}")

        return self.G

    def guardar(self, output_dir: Path):
        """Guarda el grafo en JSON y pickle."""
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

        # JSON (para inspección)
        graph_data = nx.node_link_data(self.G)
        with open(output_dir / 'normas_graph.json', 'w', encoding='utf-8') as f:
            json.dump(graph_data, f, ensure_ascii=False, indent=2)

        # Pickle (para carga rápida)
        with open(output_dir / 'normas_graph.pkl', 'wb') as f:
            pickle.dump(self.G, f)

        print(f"\nGuardado en {output_dir}")

    @classmethod
    def cargar(cls, graph_dir: Path) -> nx.DiGraph:
        """Carga grafo desde disco."""
        pkl_path = Path(graph_dir) / 'normas_graph.pkl'
        if pkl_path.exists():
            with open(pkl_path, 'rb') as f:
                return pickle.load(f)

        json_path = Path(graph_dir) / 'normas_graph.json'
        with open(json_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        return nx.node_link_graph(data)


class NormaGraphQuery:
    """Consultas sobre el grafo de normas."""

    def __init__(self, G: nx.DiGraph):
        self.G = G

    def donde_se_define(self, concepto: str) -> List[Dict]:
        """¿En qué normas se define un concepto?"""
        concepto_id = f"concepto:{concepto.lower()}"

        # Buscar match exacto o parcial
        resultados = []
        for node, d in self.G.nodes(data=True):
            if d.get('tipo_nodo') != 'concepto':
                continue
            if concepto.lower() in node.lower():
                for pred in self.G.predecessors(node):
                    edge_data = self.G.edges[pred, node]
                    if edge_data.get('relacion') == 'define':
                        norma = self.G.nodes[pred]
                        resultados.append({
                            'id_norma': pred,
                            'tipo': norma.get('tipo', ''),
                            'numero': norma.get('numero', ''),
                            'titulo': norma.get('titulo', ''),
                            'concepto': d.get('termino', ''),
                        })
        return resultados

    def que_referencia(self, id_norma: str) -> List[Dict]:
        """¿Qué normas referencia esta norma?"""
        resultados = []
        for _, target, edge_data in self.G.out_edges(id_norma, data=True):
            if edge_data.get('relacion') in ('referencia', 'alias'):
                norma = self.G.nodes.get(target, {})
                if norma.get('tipo_nodo') == 'norma':
                    resultados.append({
                        'id_norma': target,
                        'tipo': norma.get('tipo', ''),
                        'numero': norma.get('numero', ''),
                        'titulo': norma.get('titulo', ''),
                        'via': edge_data['relacion'],
                    })
        return resultados

    def quien_referencia(self, id_norma: str) -> List[Dict]:
        """¿Qué normas referencian a esta norma?"""
        resultados = []
        for source, _, edge_data in self.G.in_edges(id_norma, data=True):
            if edge_data.get('relacion') in ('referencia', 'alias'):
                norma = self.G.nodes.get(source, {})
                if norma.get('tipo_nodo') == 'norma':
                    resultados.append({
                        'id_norma': source,
                        'tipo': norma.get('tipo', ''),
                        'numero': norma.get('numero', ''),
                        'titulo': norma.get('titulo', ''),
                        'via': edge_data['relacion'],
                    })
        return resultados

    def contexto_para_query(self, query: str) -> Dict[str, float]:
        """
        Dado una query, retorna boost por norma basado en el grafo.

        Si la query menciona un concepto definido en norma X,
        da boost a X y a normas relacionadas.
        """
        boosts = defaultdict(lambda: 1.0)
        query_lower = query.lower()

        # Normalizar query: "C.O.M.A." → "coma", mantener original también
        query_normalizada = re.sub(r'\.', '', query_lower)

        # Buscar conceptos mencionados en la query
        for node, d in self.G.nodes(data=True):
            if d.get('tipo_nodo') != 'concepto':
                continue
            termino = d.get('termino', '').lower()
            variantes = d.get('variantes', [termino])
            if len(termino) < 2:
                continue
            # Matchear contra query original y normalizada
            match = any(v in query_lower or v in query_normalizada
                       for v in variantes)
            if not match:
                match = termino in query_lower or termino in query_normalizada
            if match:
                # Boost a normas que definen este concepto
                for pred in self.G.predecessors(node):
                    edge = self.G.edges[pred, node]
                    if edge.get('relacion') == 'define':
                        boosts[pred] = max(boosts[pred], 2.0)
                        # Boost menor a normas que referencian la definitoria
                        for ref_source, _, ref_edge in self.G.in_edges(pred, data=True):
                            if ref_edge.get('relacion') in ('referencia', 'alias'):
                                boosts[ref_source] = max(boosts[ref_source], 1.3)

        return dict(boosts)


def main():
    import argparse

    parser = argparse.ArgumentParser(description='Construye grafo de normas legales')
    parser.add_argument('--normas-dir', type=Path,
                        default=Path(__file__).parent.parent.parent / 'data' / 'normas_completas')
    parser.add_argument('--config-dir', type=Path,
                        default=Path(__file__).parent.parent.parent / 'config')
    parser.add_argument('--output-dir', type=Path,
                        default=Path(__file__).parent.parent.parent / 'data' / 'norma_graph')
    parser.add_argument('--query', type=str, default=None,
                        help='Query de prueba para probar el grafo')

    args = parser.parse_args()

    builder = NormaGraphBuilder(args.normas_dir, args.config_dir)
    G = builder.build()
    builder.guardar(args.output_dir)

    # Queries de prueba
    query_engine = NormaGraphQuery(G)

    print("\n" + "="*60)
    print("PRUEBAS DE CONSULTA")
    print("="*60)

    # Test: ¿dónde se define algo?
    for termino in ["Transmisión", "potencia", "concesión", "tarifa"]:
        resultados = query_engine.donde_se_define(termino)
        if resultados:
            print(f"\n  ¿Dónde se define '{termino}'?")
            for r in resultados[:3]:
                print(f"    → {r['tipo']} {r['numero']}: {r['titulo'][:60]}")

    if args.query:
        print(f"\n  Boost para query: \"{args.query}\"")
        boosts = query_engine.contexto_para_query(args.query)
        for id_norma, boost in sorted(boosts.items(), key=lambda x: -x[1])[:5]:
            d = G.nodes.get(id_norma, {})
            print(f"    [{boost:.1f}x] {d.get('tipo','')} {d.get('numero','')} - {d.get('titulo','')[:60]}")


if __name__ == '__main__':
    main()
