#!/usr/bin/env python3
"""
Descarga las próximas 100 normas que NO estén descargadas.

Simple y directo: toma las primeras 100 pendientes, sin importar importancia.
"""

import asyncio
import json
import sys
from pathlib import Path
from datetime import datetime
import time

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.crawlers.norm_detail_crawler_OPTIMIZED import NormDetailCrawlerOptimized


def get_output_path(norma: dict) -> Path:
    """Obtener ruta donde se guarda una norma."""
    base = Path("data/normas_completas")
    tipo = norma.get('tipo', 'otros').lower()
    numero = norma.get('numero', 'sin_numero')

    tipo_folder = {
        'DECRETO': 'decretos',
        'LEY': 'leyes',
        'DFL': 'dfl',
        'RESOLUCION': 'resoluciones',
        'RESOLUCIÓN': 'resoluciones',
    }.get(tipo.upper(), 'otros')

    folder = base / tipo_folder
    folder.mkdir(parents=True, exist_ok=True)

    filename = f"{tipo.lower()}_{numero}.json"
    return folder / filename


def is_downloaded(norma: dict) -> bool:
    """Verificar si una norma ya fue descargada."""
    output_path = get_output_path(norma)

    if not output_path.exists():
        return False

    # Verificar que tenga texto_completo
    try:
        with open(output_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
            return len(data.get('texto_completo', '')) > 500
    except:
        return False


def save_norm(norm_data, norma_original: dict) -> bool:
    """Guardar norma descargada."""
    if not norm_data:
        return False

    output_path = get_output_path(norma_original)

    try:
        from dataclasses import asdict
        data = asdict(norm_data) if hasattr(norm_data, '__dict__') else norm_data

        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

        return True
    except Exception as e:
        print(f"    ❌ Error guardando: {e}")
        return False


async def main():
    print("=" * 70)
    print("🚀 DESCARGA DE LAS PRÓXIMAS 100 NORMAS")
    print("=" * 70)

    # Cargar normas
    normas_file = Path("data/busquedas/normas_completas.json")
    with open(normas_file, 'r', encoding='utf-8') as f:
        data = json.load(f)

    normas = data['normas']
    print(f"\n📊 Total en dataset: {len(normas)}")

    # Filtrar pendientes
    pendientes = [n for n in normas if not is_downloaded(n)]
    print(f"📂 Ya descargadas: {len(normas) - len(pendientes)}")
    print(f"📥 Pendientes: {len(pendientes)}")

    # Tomar las primeras 100 pendientes
    to_download = pendientes[:100]
    print(f"\n🎯 Descargando: {len(to_download)} normas")

    if not to_download:
        print("\n✅ ¡No hay normas pendientes!")
        return

    print(f"\n⏱️  Estimación: ~{len(to_download) * 15 / 60:.1f} minutos")
    print(f"   (5s descarga + 10s delay anti-bloqueo)")

    # Confirmar
    response = input("\n¿Continuar? (y/N): ")
    if response.lower() != 'y':
        print("❌ Cancelado")
        return

    # Descargar
    print("\n" + "-" * 70)
    print("📥 INICIANDO DESCARGA...")
    print("-" * 70)

    stats = {'éxitos': 0, 'errores': 0}
    start_time = time.time()

    async with NormDetailCrawlerOptimized(headless=True, validate=True) as crawler:
        for i, norma in enumerate(to_download, 1):
            id_norma = norma.get('id_norma')
            tipo = norma.get('tipo', '???')
            numero = norma.get('numero', '???')

            # Progreso
            porcentaje = (i / len(to_download)) * 100
            bar_length = 30
            filled = int(bar_length * i / len(to_download))
            bar = '█' * filled + '░' * (bar_length - filled)

            # ETA
            if i > 1:
                elapsed = time.time() - start_time
                avg_time = elapsed / i
                remaining = (len(to_download) - i) * avg_time
                eta_min = remaining / 60
                eta_str = f"{eta_min:.1f} min"
            else:
                eta_str = "calculando..."

            print(f"\n[{i}/{len(to_download)}] {bar} {porcentaje:.1f}%")
            print(f"  📥 {tipo} {numero} (ID: {id_norma})")
            print(f"  ⏱️  ETA: {eta_str}")

            try:
                # Descargar
                norm_data = await crawler.fetch_norm(id_norma)

                # Guardar
                if norm_data:
                    # Validación
                    val = norm_data.validation_status
                    val_emoji = "✅" if val['status'] == 'VALID' else "⚠️ " if val['status'] == 'WARNING' else "❌"

                    success = save_norm(norm_data, norma)
                    if success:
                        stats['éxitos'] += 1
                        print(f"  {val_emoji} {len(norm_data.texto_completo)} chars | {val.get('num_articulos', 0)} arts | {val['status']}")
                    else:
                        stats['errores'] += 1
                        print(f"  ❌ Error al guardar")
                else:
                    stats['errores'] += 1
                    print(f"  ❌ Fallo en descarga")

                # Delay anti-bloqueo
                if i < len(to_download):
                    await asyncio.sleep(10)

            except KeyboardInterrupt:
                print("\n\n⚠️  Interrumpido por usuario")
                break

            except Exception as e:
                print(f"  ❌ Error: {e}")
                stats['errores'] += 1

    # Resumen
    elapsed_total = time.time() - start_time
    print("\n" + "=" * 70)
    print("✅ DESCARGA COMPLETADA")
    print("=" * 70)
    print(f"\n📊 Resumen:")
    print(f"  ✅ Éxitos: {stats['éxitos']}")
    print(f"  ❌ Errores: {stats['errores']}")
    print(f"  ⏱️  Tiempo total: {elapsed_total / 60:.1f} minutos")
    print(f"\n💾 Archivos guardados en: data/normas_completas/")
    print("=" * 70)


if __name__ == "__main__":
    asyncio.run(main())
