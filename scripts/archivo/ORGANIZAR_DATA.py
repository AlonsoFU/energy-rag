#!/usr/bin/env python3
"""
Organizar carpeta data/busquedas/ que está desordenada.

Crea estructura:
data/
├── busquedas/
│   └── normas_completas.json          # ← SOLO EL PRINCIPAL
├── analisis/                           # ← Análisis y casos de uso
│   ├── casos/
│   ├── clusters/
│   └── relaciones/
├── logs/                               # ← Logs y verificaciones
├── docs/                               # ← Documentación markdown
└── temp/                               # ← Archivos temporales/experimentales
"""

import shutil
from pathlib import Path
import json

def organizar_data():
    """Reorganizar carpeta data/busquedas/."""

    base = Path("data")
    busquedas = base / "busquedas"

    # Crear nueva estructura
    folders = {
        'analisis': base / 'analisis',
        'analisis_casos': base / 'analisis' / 'casos',
        'analisis_clusters': base / 'analisis' / 'clusters',
        'analisis_relaciones': base / 'analisis' / 'relaciones',
        'logs': base / 'logs',
        'docs_data': base / 'docs_data',
        'temp': base / 'temp'
    }

    for folder in folders.values():
        folder.mkdir(parents=True, exist_ok=True)

    print("=" * 70)
    print("🗂️  ORGANIZANDO data/busquedas/")
    print("=" * 70)

    # Mapeo de archivos a destinos
    moves = {
        # ANÁLISIS - Casos de uso
        'analisis_caso_potencia.json': folders['analisis_casos'],
        'caso_compliance_generadora.json': folders['analisis_casos'],

        # ANÁLISIS - Clusters
        'analisis_clusters_implicitos.json': folders['analisis_clusters'],

        # ANÁLISIS - Relaciones
        'analisis_relaciones.json': folders['analisis_relaciones'],
        'vinculaciones_estructuradas.json': folders['analisis_relaciones'],

        # ANÁLISIS - Ampliado (metadata extra)
        'analisis_ampliado.json': folders['analisis'],
        'transacciones_economicas.json': folders['analisis'],

        # LOGS - Verificaciones
        'verificacion_pendientes.json': folders['logs'],
        'verificacion_pendientes_manual.json': folders['logs'],
        'errores_descarga.json': folders['logs'],
        'log_problemas.json': folders['logs'],

        # DOCS - Markdown
        'ANALISIS_ESTRUCTURACION.md': folders['docs_data'],
        'MAPA_NORMAS.md': folders['docs_data'],
        'RESUMEN_DESCARGA_FINAL.md': folders['docs_data'],
        'RESUMEN_FINAL_ACTUALIZADO.md': folders['docs_data'],

        # TEMP - Archivos temporales/experimentales
        'analisis_estructura.json': folders['temp'],
        'benchmark_vectordb.json': folders['temp'],
        'decreto62_html.html': folders['temp'],
        'decretos_sector_electrico.json': folders['temp'],
        'normas_ids_conocidos.json': folders['temp'],
        'normas_por_tema_solicitado.json': folders['temp'],
        'normas_temas_electricos.json': folders['temp'],
        'resumen_final.json': folders['temp'],
    }

    # Ejecutar movimientos
    moved = 0
    for filename, dest_folder in moves.items():
        src = busquedas / filename
        if src.exists():
            dest = dest_folder / filename
            print(f"  📦 {filename}")
            print(f"     → {dest_folder.relative_to(base)}/")
            shutil.move(str(src), str(dest))
            moved += 1

    print(f"\n✅ Movidos {moved} archivos")

    # Verificar qué queda en busquedas/
    remaining = list(busquedas.glob('*'))
    remaining_files = [f for f in remaining if f.is_file()]

    print(f"\n📂 Archivos que permanecen en busquedas/:")
    for f in remaining_files:
        size = f.stat().st_size / 1024
        print(f"  ✓ {f.name} ({size:.1f} KB)")

    # Crear README en cada carpeta
    readmes = {
        folders['analisis_casos']: "# Casos de uso y análisis de compliance\n\nEjemplos de búsquedas y análisis de casos reales.",
        folders['analisis_clusters']: "# Análisis de clusters\n\nAgrupaciones automáticas de normas relacionadas.",
        folders['analisis_relaciones']: "# Análisis de relaciones\n\nVinculaciones entre normas (modifica, deroga, reglamenta).",
        folders['logs']: "# Logs y verificaciones\n\nRegistros de descargas, errores y verificaciones.",
        folders['docs_data']: "# Documentación de datos\n\nResúmenes y mapas de la estructura de normas.",
        folders['temp']: "# Archivos temporales\n\nArchivos experimentales y de prueba. Pueden eliminarse."
    }

    for folder, content in readmes.items():
        readme = folder / "README.md"
        if not readme.exists():
            with open(readme, 'w', encoding='utf-8') as f:
                f.write(content)

    print(f"\n📝 Creados {len(readmes)} READMEs")

    # Resumen de nueva estructura
    print("\n" + "=" * 70)
    print("✅ ESTRUCTURA ORGANIZADA")
    print("=" * 70)
    print("""
data/
├── busquedas/
│   └── normas_completas.json          ← Dataset principal (2,031 normas)
├── analisis/
│   ├── casos/                         ← Casos de compliance
│   ├── clusters/                      ← Clustering automático
│   └── relaciones/                    ← Análisis de vinculaciones
├── logs/                              ← Logs de descarga
├── docs_data/                         ← Documentación markdown
└── temp/                              ← Archivos temporales

✨ Carpeta limpia y organizada
    """)


if __name__ == "__main__":
    organizar_data()
