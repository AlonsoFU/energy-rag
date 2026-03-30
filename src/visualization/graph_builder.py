"""
Constructor de grafo de relaciones entre normas.
Usa NetworkX para el grafo y Pyvis para visualización HTML.
"""

import networkx as nx
from pyvis.network import Network
from pathlib import Path
from typing import Optional, List, Dict


class NormGraphBuilder:
    """Constructor de grafo de relaciones entre normas."""

    # Colores por tipo de norma
    NODE_COLORS = {
        'LEY': '#2E86AB',        # Azul
        'DECRETO': '#A23B72',    # Magenta
        'DFL': '#F18F01',        # Naranja
        'DL': '#C73E1D',         # Rojo oscuro
        'RESOLUCION': '#3B7A57', # Verde
        'AUTO': '#6C757D',       # Gris
        'OTRO': '#6C757D',       # Gris
    }

    # Colores por tipo de relación
    EDGE_COLORS = {
        'MODIFICA': '#FFA500',       # Naranja
        'DEROGA': '#DC3545',          # Rojo
        'DEROGA_PARCIALMENTE': '#FF6B6B',
        'SUSTITUYE': '#6F42C1',       # Púrpura
        'REGLAMENTA': '#28A745',      # Verde
        'COMPLEMENTA': '#17A2B8',     # Cyan
        'AGREGA': '#FFC107',          # Amarillo
        'REFERENCIA': '#6C757D',      # Gris
    }

    # Colores por estado
    STATUS_BORDER = {
        'VIGENTE': '#28A745',     # Verde
        'DEROGADA': '#DC3545',    # Rojo
        'MODIFICADA': '#FFC107',  # Amarillo
        'DESCONOCIDO': '#6C757D', # Gris
    }

    def __init__(self, session):
        self.session = session
        self.graph = nx.DiGraph()

    def build_from_database(self):
        """Construir grafo desde la base de datos."""
        from src.database.models import Norm, NormRelationship

        # Cargar normas con relaciones
        norms_with_relations = set()

        # Primero identificar normas con relaciones
        relationships = self.session.query(NormRelationship).all()
        for rel in relationships:
            norms_with_relations.add(rel.source_norm_id)
            norms_with_relations.add(rel.target_norm_id)

        print(f"📊 Normas con relaciones: {len(norms_with_relations)}")
        print(f"📊 Total relaciones: {len(relationships)}")

        # Agregar nodos
        for norm_id in norms_with_relations:
            norm = self.session.get(Norm, norm_id)
            if norm:
                self._add_norm_node(norm)

        # Agregar aristas
        for rel in relationships:
            self._add_relationship_edge(rel)

        return self.graph

    def _add_norm_node(self, norm):
        """Agregar nodo de norma al grafo."""
        tipo = norm.tipo.value if norm.tipo else 'OTRO'
        estado = norm.estado.value if norm.estado else 'DESCONOCIDO'

        self.graph.add_node(
            norm.id,
            label=norm.nombre_corto,
            title=f"{norm.nombre_corto}\n{norm.titulo[:100]}...\n\nAño: {norm.año}\nEstado: {estado}",
            tipo=tipo,
            estado=estado,
            año=norm.año,
            color=self.NODE_COLORS.get(tipo, '#6C757D'),
            borderWidth=3,
            borderColor=self.STATUS_BORDER.get(estado, '#6C757D'),
        )

    def _add_relationship_edge(self, rel):
        """Agregar arista de relación al grafo."""
        rel_type = rel.relationship_type.value if rel.relationship_type else 'REFERENCIA'

        self.graph.add_edge(
            rel.source_norm_id,
            rel.target_norm_id,
            title=rel_type,
            label=rel_type[:3],  # Abreviatura
            color=self.EDGE_COLORS.get(rel_type, '#6C757D'),
            arrows='to',
            width=2,
        )

    def export_to_pyvis(
        self,
        output_path: str = "docs/norm_graph.html",
        height: str = "900px",
        width: str = "100%"
    ):
        """Exportar grafo a HTML interactivo con Pyvis."""

        if len(self.graph.nodes) == 0:
            print("⚠️  Grafo vacío, nada que exportar")
            return None

        # Crear red Pyvis
        net = Network(
            height=height,
            width=width,
            bgcolor="#222222",
            font_color="white",
            directed=True,
            notebook=False,
            cdn_resources='remote'
        )

        # Configurar física
        net.set_options("""
        {
            "nodes": {
                "font": {"size": 14},
                "shape": "box",
                "shadow": true
            },
            "edges": {
                "font": {"size": 10, "align": "middle"},
                "smooth": {"type": "curvedCW", "roundness": 0.2}
            },
            "physics": {
                "forceAtlas2Based": {
                    "gravitationalConstant": -50,
                    "centralGravity": 0.01,
                    "springLength": 100,
                    "springConstant": 0.08
                },
                "maxVelocity": 50,
                "solver": "forceAtlas2Based",
                "timestep": 0.35,
                "stabilization": {
                    "enabled": true,
                    "iterations": 1000
                }
            },
            "interaction": {
                "hover": true,
                "tooltipDelay": 100,
                "navigationButtons": true,
                "keyboard": true
            }
        }
        """)

        # Transferir nodos
        for node_id in self.graph.nodes:
            node_data = self.graph.nodes[node_id]
            net.add_node(
                node_id,
                label=node_data.get('label', str(node_id)),
                title=node_data.get('title', ''),
                color=node_data.get('color', '#6C757D'),
                borderWidth=node_data.get('borderWidth', 1),
                borderWidthSelected=4,
            )

        # Transferir aristas
        for source, target in self.graph.edges:
            edge_data = self.graph.edges[source, target]
            net.add_edge(
                source,
                target,
                title=edge_data.get('title', ''),
                label=edge_data.get('label', ''),
                color=edge_data.get('color', '#6C757D'),
                width=edge_data.get('width', 1),
            )

        # Crear directorio si no existe
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)

        # Guardar HTML
        net.save_graph(output_path)
        print(f"✅ Grafo exportado a: {output_path}")

        return output_path

    def export_to_graphml(self, output_path: str = "docs/norm_graph.graphml"):
        """Exportar a GraphML para Gephi."""
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        nx.write_graphml(self.graph, output_path)
        print(f"✅ GraphML exportado a: {output_path}")
        return output_path

    def get_stats(self) -> dict:
        """Obtener estadísticas del grafo."""
        return {
            'nodes': len(self.graph.nodes),
            'edges': len(self.graph.edges),
            'density': nx.density(self.graph) if len(self.graph.nodes) > 0 else 0,
            'components': nx.number_weakly_connected_components(self.graph) if len(self.graph.nodes) > 0 else 0,
        }


def create_visualization(db_path: str = "db/bcn_norms.db", output_path: str = "docs/norm_graph.html"):
    """Crear visualización del grafo de normas."""
    from src.database.models import get_engine, get_session

    print("=" * 60)
    print("VISUALIZACIÓN DE GRAFO DE NORMAS")
    print("=" * 60)

    engine = get_engine(db_path)
    session = get_session(engine)

    builder = NormGraphBuilder(session)
    builder.build_from_database()

    stats = builder.get_stats()
    print(f"\n📊 Estadísticas del grafo:")
    print(f"   Nodos: {stats['nodes']}")
    print(f"   Aristas: {stats['edges']}")
    print(f"   Componentes: {stats['components']}")

    html_path = builder.export_to_pyvis(output_path)
    builder.export_to_graphml(output_path.replace('.html', '.graphml'))

    session.close()
    return html_path


if __name__ == "__main__":
    create_visualization()
