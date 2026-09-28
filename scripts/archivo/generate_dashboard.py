#!/usr/bin/env python3
"""
Dashboard HTML para visualizar organización de normas BCN.
"""

import sys
import json
from pathlib import Path
from collections import Counter

sys.path.insert(0, str(Path(__file__).parent.parent))

import plotly.graph_objects as go
from plotly.subplots import make_subplots

from src.database.models import Norm, NormType, get_engine, get_session


def generate_dashboard(db_path: str = "db/bcn_norms.db", output_path: str = "docs/dashboard.html"):
    """Generar dashboard de organización de normas."""

    print("=" * 60)
    print("DASHBOARD DE NORMAS BCN")
    print("=" * 60)

    engine = get_engine(db_path)
    session = get_session(engine)

    # Cargar todas las normas
    norms = session.query(Norm).all()
    print(f"\nTotal normas: {len(norms)}")

    # Preparar datos
    tipos = Counter()
    años = Counter()
    organismos = Counter()
    materias_count = Counter()
    tipo_por_año = {}

    for norm in norms:
        # Por tipo
        tipo = norm.tipo.value if norm.tipo else 'OTRO'
        tipos[tipo] += 1

        # Por año
        if norm.año:
            años[norm.año] += 1
            if norm.año not in tipo_por_año:
                tipo_por_año[norm.año] = Counter()
            tipo_por_año[norm.año][tipo] += 1

        # Por organismo
        org = norm.organismo_normalizado or 'OTRO'
        organismos[org] += 1

        # Por materia
        if norm.materias:
            try:
                mats = json.loads(norm.materias)
                for m in mats:
                    materias_count[m] += 1
            except:
                pass

    session.close()

    # Colores por tipo
    colores_tipo = {
        'LEY': '#2E86AB',
        'DECRETO': '#A23B72',
        'DFL': '#F18F01',
        'DL': '#C73E1D',
        'RESOLUCION': '#3B7A57',
        'AUTO': '#6C757D',
        'OTRO': '#6C757D',
    }

    # Crear figura con subplots
    fig = make_subplots(
        rows=3, cols=2,
        subplot_titles=(
            'Distribución por Tipo de Norma',
            'Top 10 Organismos',
            'Normas por Año',
            'Top 15 Materias',
            'Evolución por Tipo',
            ''
        ),
        specs=[
            [{"type": "pie"}, {"type": "bar"}],
            [{"type": "bar"}, {"type": "bar"}],
            [{"type": "scatter", "colspan": 2}, None]
        ],
        vertical_spacing=0.12,
        horizontal_spacing=0.1
    )

    # 1. Pie chart - Tipos
    tipo_labels = list(tipos.keys())
    tipo_values = list(tipos.values())
    tipo_colors = [colores_tipo.get(t, '#6C757D') for t in tipo_labels]

    fig.add_trace(
        go.Pie(
            labels=tipo_labels,
            values=tipo_values,
            marker_colors=tipo_colors,
            textinfo='label+percent',
            hovertemplate='%{label}: %{value} normas<extra></extra>'
        ),
        row=1, col=1
    )

    # 2. Bar chart - Organismos (top 10)
    org_sorted = sorted(organismos.items(), key=lambda x: x[1], reverse=True)[:10]
    org_labels = [o[0] for o in org_sorted]
    org_values = [o[1] for o in org_sorted]

    fig.add_trace(
        go.Bar(
            x=org_values,
            y=org_labels,
            orientation='h',
            marker_color='#2E86AB',
            hovertemplate='%{y}: %{x} normas<extra></extra>'
        ),
        row=1, col=2
    )

    # 3. Bar chart - Timeline años
    años_sorted = sorted(años.items())
    año_labels = [str(a[0]) for a in años_sorted]
    año_values = [a[1] for a in años_sorted]

    fig.add_trace(
        go.Bar(
            x=año_labels,
            y=año_values,
            marker_color='#3B7A57',
            hovertemplate='%{x}: %{y} normas<extra></extra>'
        ),
        row=2, col=1
    )

    # 4. Bar chart - Materias (top 15)
    mat_sorted = sorted(materias_count.items(), key=lambda x: x[1], reverse=True)[:15]
    mat_labels = [m[0][:25] for m in mat_sorted]  # Truncar nombres largos
    mat_values = [m[1] for m in mat_sorted]

    fig.add_trace(
        go.Bar(
            x=mat_values,
            y=mat_labels,
            orientation='h',
            marker_color='#F18F01',
            hovertemplate='%{y}: %{x} normas<extra></extra>'
        ),
        row=2, col=2
    )

    # 5. Line chart - Evolución por tipo (últimos 30 años)
    años_recientes = sorted([a for a in tipo_por_año.keys() if a >= 1995])

    for tipo in ['DECRETO', 'RESOLUCION', 'LEY', 'DFL']:
        valores = [tipo_por_año.get(año, {}).get(tipo, 0) for año in años_recientes]
        fig.add_trace(
            go.Scatter(
                x=[str(a) for a in años_recientes],
                y=valores,
                mode='lines+markers',
                name=tipo,
                line=dict(color=colores_tipo.get(tipo, '#6C757D'), width=2),
                hovertemplate=f'{tipo}: %{{y}} en %{{x}}<extra></extra>'
            ),
            row=3, col=1
        )

    # Layout general
    fig.update_layout(
        title={
            'text': 'Normativa Eléctrica Chilena - BCN',
            'x': 0.5,
            'font': {'size': 24}
        },
        height=1200,
        showlegend=True,
        legend=dict(
            orientation="h",
            yanchor="bottom",
            y=-0.05,
            xanchor="center",
            x=0.5
        ),
        template='plotly_white',
        font=dict(family="Arial", size=12)
    )

    # Ajustar ejes
    fig.update_yaxes(categoryorder='total ascending', row=1, col=2)
    fig.update_yaxes(categoryorder='total ascending', row=2, col=2)
    fig.update_xaxes(tickangle=45, row=2, col=1)
    fig.update_xaxes(tickangle=45, row=3, col=1)

    # Guardar HTML
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    fig.write_html(output_path, include_plotlyjs=True, full_html=True)

    print(f"\n✅ Dashboard generado: {output_path}")

    # Resumen
    print(f"\n📊 Resumen:")
    print(f"   Total normas: {len(norms)}")
    print(f"   Tipos: {len(tipos)}")
    print(f"   Rango años: {min(años.keys())}-{max(años.keys())}")
    print(f"   Organismos únicos: {len(organismos)}")
    print(f"   Materias únicas: {len(materias_count)}")

    return output_path


if __name__ == "__main__":
    path = generate_dashboard()
    print(f"\nAbre: xdg-open {path}")
