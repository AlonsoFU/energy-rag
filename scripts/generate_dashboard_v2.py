#!/usr/bin/env python3
"""
Dashboard HTML con filtros por temática.
"""

import sys
import json
from pathlib import Path
from collections import Counter, defaultdict

sys.path.insert(0, str(Path(__file__).parent.parent))

import plotly.graph_objects as go
from plotly.subplots import make_subplots

from src.database.models import Norm, get_engine, get_session


def generate_dashboard(db_path: str = "db/bcn_norms.db", output_path: str = "docs/dashboard.html"):
    """Generar dashboard con filtros por temática."""

    print("=" * 60)
    print("DASHBOARD DE NORMAS BCN v2")
    print("=" * 60)

    engine = get_engine(db_path)
    session = get_session(engine)
    norms = session.query(Norm).all()
    print(f"\nTotal normas: {len(norms)}")

    # Colores
    colores_tipo = {
        'LEY': '#2E86AB',
        'DECRETO': '#A23B72',
        'DFL': '#F18F01',
        'DL': '#C73E1D',
        'RESOLUCION': '#3B7A57',
        'OTRO': '#6C757D',
    }

    colores_materia = [
        '#1f77b4', '#ff7f0e', '#2ca02c', '#d62728', '#9467bd',
        '#8c564b', '#e377c2', '#7f7f7f', '#bcbd22', '#17becf',
        '#aec7e8', '#ffbb78', '#98df8a', '#ff9896', '#c5b0d5',
        '#c49c94', '#f7b6d2', '#c7c7c7', '#dbdb8d', '#9edae5',
        '#393b79', '#637939'
    ]

    # Preparar datos por materia
    materias_data = defaultdict(lambda: {
        'normas': [],
        'tipos': Counter(),
        'años': Counter(),
        'organismos': Counter()
    })

    for norm in norms:
        tipo = norm.tipo.value if norm.tipo else 'OTRO'
        año = norm.año
        org = norm.organismo_normalizado or 'OTRO'

        if norm.materias:
            try:
                mats = json.loads(norm.materias)
                for mat in mats:
                    materias_data[mat]['normas'].append(norm)
                    materias_data[mat]['tipos'][tipo] += 1
                    if año:
                        materias_data[mat]['años'][año] += 1
                    materias_data[mat]['organismos'][org] += 1
            except:
                pass

    session.close()

    # Ordenar materias por cantidad
    materias_sorted = sorted(materias_data.items(), key=lambda x: len(x[1]['normas']), reverse=True)
    materias_names = [m[0] for m in materias_sorted]

    # ============================================
    # Crear HTML con tabs interactivos
    # ============================================

    html_content = """
<!DOCTYPE html>
<html lang="es">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Normativa Electrica Chilena - BCN</title>
    <script src="https://cdn.plot.ly/plotly-latest.min.js"></script>
    <style>
        * { box-sizing: border-box; margin: 0; padding: 0; }
        body {
            font-family: 'Segoe UI', Arial, sans-serif;
            background: #1a1a2e;
            color: #eee;
            min-height: 100vh;
        }
        .header {
            background: linear-gradient(135deg, #16213e, #1a1a2e);
            padding: 20px;
            text-align: center;
            border-bottom: 2px solid #0f3460;
        }
        .header h1 { color: #e94560; margin-bottom: 5px; }
        .header p { color: #aaa; }
        .stats-bar {
            display: flex;
            justify-content: center;
            gap: 40px;
            padding: 15px;
            background: #16213e;
            flex-wrap: wrap;
        }
        .stat { text-align: center; }
        .stat-num { font-size: 28px; font-weight: bold; color: #e94560; }
        .stat-label { font-size: 12px; color: #888; }
        .container { max-width: 1400px; margin: 0 auto; padding: 20px; }
        .tabs {
            display: flex;
            flex-wrap: wrap;
            gap: 5px;
            margin-bottom: 20px;
            padding: 10px;
            background: #16213e;
            border-radius: 8px;
        }
        .tab {
            padding: 8px 16px;
            background: #0f3460;
            border: none;
            border-radius: 5px;
            color: #aaa;
            cursor: pointer;
            font-size: 13px;
            transition: all 0.2s;
        }
        .tab:hover { background: #1a1a4e; color: #fff; }
        .tab.active { background: #e94560; color: #fff; }
        .tab-content { display: none; }
        .tab-content.active { display: block; }
        .grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(500px, 1fr)); gap: 20px; }
        .chart-box {
            background: #16213e;
            border-radius: 10px;
            padding: 15px;
            min-height: 400px;
        }
        .chart-title {
            color: #e94560;
            font-size: 14px;
            margin-bottom: 10px;
            padding-bottom: 10px;
            border-bottom: 1px solid #0f3460;
        }
        .normas-list {
            max-height: 500px;
            overflow-y: auto;
            background: #0f3460;
            border-radius: 8px;
            padding: 10px;
        }
        .norma-item {
            padding: 10px;
            border-bottom: 1px solid #1a1a2e;
            font-size: 13px;
        }
        .norma-item:last-child { border-bottom: none; }
        .norma-tipo {
            display: inline-block;
            padding: 2px 8px;
            border-radius: 3px;
            font-size: 11px;
            font-weight: bold;
            margin-right: 8px;
        }
        .tipo-LEY { background: #2E86AB; }
        .tipo-DECRETO { background: #A23B72; }
        .tipo-DFL { background: #F18F01; }
        .tipo-RESOLUCION { background: #3B7A57; }
        .tipo-OTRO { background: #6C757D; }
        .norma-year { color: #888; font-size: 11px; }
        .norma-title { color: #ccc; margin-top: 5px; line-height: 1.4; }
        .full-width { grid-column: 1 / -1; }
    </style>
</head>
<body>
    <div class="header">
        <h1>Normativa Electrica Chilena</h1>
        <p>Biblioteca del Congreso Nacional - Sector Electrico</p>
    </div>

    <div class="stats-bar">
        <div class="stat">
            <div class="stat-num">""" + str(len(norms)) + """</div>
            <div class="stat-label">NORMAS TOTALES</div>
        </div>
        <div class="stat">
            <div class="stat-num">""" + str(len(materias_names)) + """</div>
            <div class="stat-label">TEMATICAS</div>
        </div>
        <div class="stat">
            <div class="stat-num">1893-2026</div>
            <div class="stat-label">RANGO TEMPORAL</div>
        </div>
    </div>

    <div class="container">
        <div class="tabs">
            <button class="tab active" onclick="showTab('general')">Vista General</button>
"""

    # Agregar tabs por materia
    for i, mat in enumerate(materias_names):
        count = len(materias_data[mat]['normas'])
        html_content += f'            <button class="tab" onclick="showTab(\'mat{i}\')">{mat} ({count})</button>\n'

    html_content += """        </div>

        <!-- Tab General -->
        <div id="general" class="tab-content active">
            <div class="grid">
                <div class="chart-box">
                    <div class="chart-title">Distribucion por Tipo de Norma</div>
                    <div id="chart-tipos"></div>
                </div>
                <div class="chart-box">
                    <div class="chart-title">Top Organismos</div>
                    <div id="chart-orgs"></div>
                </div>
                <div class="chart-box full-width">
                    <div class="chart-title">Normas por Tematica</div>
                    <div id="chart-materias"></div>
                </div>
                <div class="chart-box full-width">
                    <div class="chart-title">Timeline por Año</div>
                    <div id="chart-timeline"></div>
                </div>
            </div>
        </div>
"""

    # Agregar contenido para cada materia
    for i, (mat, data) in enumerate(materias_sorted):
        normas_html = ""
        # Ordenar normas por año descendente
        normas_sorted = sorted(data['normas'], key=lambda n: n.año or 0, reverse=True)
        for norm in normas_sorted[:50]:  # Limitar a 50
            tipo = norm.tipo.value if norm.tipo else 'OTRO'
            titulo = norm.titulo[:150] + "..." if len(norm.titulo) > 150 else norm.titulo
            normas_html += f'''
                <div class="norma-item">
                    <span class="norma-tipo tipo-{tipo}">{tipo}</span>
                    <span class="norma-year">{norm.año or 'S/F'}</span>
                    <span style="color:#fff">{norm.numero or ''}</span>
                    <div class="norma-title">{titulo}</div>
                </div>'''

        html_content += f"""
        <div id="mat{i}" class="tab-content">
            <div class="grid">
                <div class="chart-box">
                    <div class="chart-title">Tipos en {mat}</div>
                    <div id="chart-mat{i}-tipos"></div>
                </div>
                <div class="chart-box">
                    <div class="chart-title">Timeline {mat}</div>
                    <div id="chart-mat{i}-timeline"></div>
                </div>
                <div class="chart-box full-width">
                    <div class="chart-title">Normas de {mat} ({len(data['normas'])} total)</div>
                    <div class="normas-list">{normas_html}
                    </div>
                </div>
            </div>
        </div>
"""

    # JavaScript para tabs y gráficos
    html_content += """
    </div>

    <script>
        function showTab(tabId) {
            document.querySelectorAll('.tab-content').forEach(c => c.classList.remove('active'));
            document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
            document.getElementById(tabId).classList.add('active');
            event.target.classList.add('active');
        }

        const coloresTipo = {
            'LEY': '#2E86AB',
            'DECRETO': '#A23B72',
            'DFL': '#F18F01',
            'DL': '#C73E1D',
            'RESOLUCION': '#3B7A57',
            'OTRO': '#6C757D'
        };

        const layout = {
            paper_bgcolor: 'rgba(0,0,0,0)',
            plot_bgcolor: 'rgba(0,0,0,0)',
            font: { color: '#ccc', size: 11 },
            margin: { t: 30, b: 40, l: 40, r: 20 }
        };

        // Gráfico de tipos general
        Plotly.newPlot('chart-tipos', [{
            type: 'pie',
            labels: """ + json.dumps(list(Counter(n.tipo.value if n.tipo else 'OTRO' for n in norms).keys())) + """,
            values: """ + json.dumps(list(Counter(n.tipo.value if n.tipo else 'OTRO' for n in norms).values())) + """,
            marker: { colors: """ + json.dumps([colores_tipo.get(t, '#6C757D') for t in Counter(n.tipo.value if n.tipo else 'OTRO' for n in norms).keys()]) + """ },
            textinfo: 'label+percent',
            hole: 0.4
        }], {...layout, height: 350});

        // Gráfico de organismos
        const orgs = """ + json.dumps(dict(Counter(n.organismo_normalizado or 'OTRO' for n in norms).most_common(10))) + """;
        Plotly.newPlot('chart-orgs', [{
            type: 'bar',
            y: Object.keys(orgs),
            x: Object.values(orgs),
            orientation: 'h',
            marker: { color: '#2E86AB' }
        }], {...layout, height: 350, margin: { ...layout.margin, l: 120 }});

        // Gráfico de materias
        const materias = """ + json.dumps({m: len(d['normas']) for m, d in materias_sorted}) + """;
        Plotly.newPlot('chart-materias', [{
            type: 'bar',
            x: Object.keys(materias),
            y: Object.values(materias),
            marker: { color: '#e94560' }
        }], {...layout, height: 300, margin: { ...layout.margin, b: 100 }});

        // Timeline general
        const años = """ + json.dumps(dict(sorted(Counter(n.año for n in norms if n.año).items()))) + """;
        Plotly.newPlot('chart-timeline', [{
            type: 'scatter',
            mode: 'lines+markers',
            x: Object.keys(años),
            y: Object.values(años),
            line: { color: '#3B7A57', width: 2 },
            marker: { size: 4 }
        }], {...layout, height: 250});
"""

    # Gráficos para cada materia
    for i, (mat, data) in enumerate(materias_sorted):
        tipos_data = dict(data['tipos'])
        años_data = dict(sorted(data['años'].items()))

        html_content += f"""
        // Gráficos materia {i}
        Plotly.newPlot('chart-mat{i}-tipos', [{{
            type: 'pie',
            labels: {json.dumps(list(tipos_data.keys()))},
            values: {json.dumps(list(tipos_data.values()))},
            marker: {{ colors: {json.dumps([colores_tipo.get(t, '#6C757D') for t in tipos_data.keys()])} }},
            hole: 0.4
        }}], {{...layout, height: 300}});

        Plotly.newPlot('chart-mat{i}-timeline', [{{
            type: 'bar',
            x: {json.dumps(list(str(a) for a in años_data.keys()))},
            y: {json.dumps(list(años_data.values()))},
            marker: {{ color: '#e94560' }}
        }}], {{...layout, height: 300}});
"""

    html_content += """
    </script>
</body>
</html>
"""

    # Guardar
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(html_content)

    print(f"\n✅ Dashboard generado: {output_path}")
    return output_path


if __name__ == "__main__":
    path = generate_dashboard()
    print(f"\nAbre: xdg-open {path}")
