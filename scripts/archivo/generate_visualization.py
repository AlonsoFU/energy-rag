#!/usr/bin/env python3
"""
Generar visualización HTML del grafo de normas.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.database.models import get_engine, get_session
from src.visualization.graph_builder import NormGraphBuilder


def main():
    print("=" * 60)
    print("VISUALIZACION DE GRAFO DE NORMAS BCN")
    print("=" * 60)

    db_path = "db/bcn_norms.db"
    output_path = "docs/norm_graph.html"

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
    graphml_path = builder.export_to_graphml(output_path.replace('.html', '.graphml'))

    session.close()

    print(f"\n🌐 Abre el archivo HTML en tu navegador:")
    print(f"   {Path(html_path).absolute()}")

    return html_path


if __name__ == "__main__":
    main()
