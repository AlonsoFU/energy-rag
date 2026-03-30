#!/usr/bin/env python3
"""
DESCARGA MASIVA: Texto completo de todas las normas BCN

Este script descarga automáticamente el texto completo con artículos
de todas las 2,031 normas del dataset.

Características:
- ✅ Progreso incremental (resume si se interrumpe)
- ✅ Delays anti-bloqueo (evita ban de BCN)
- ✅ Logging detallado con estadísticas
- ✅ Checkpoint cada 10 normas
- ✅ Barra de progreso visual
- ✅ Estimación de tiempo restante
- ✅ Manejo robusto de errores

Uso:
    python3 scripts/DOWNLOAD_ALL_NORMS.py

    # Solo TOP 50 más importantes
    python3 scripts/DOWNLOAD_ALL_NORMS.py --top 50

    # Continuar desde donde quedó
    python3 scripts/DOWNLOAD_ALL_NORMS.py --resume

    # Modo rápido (menos delays, riesgo de bloqueo)
    python3 scripts/DOWNLOAD_ALL_NORMS.py --fast

    # Ejecutar en background
    nohup python3 scripts/DOWNLOAD_ALL_NORMS.py &> download.log &
"""

import asyncio
import json
import sys
from pathlib import Path
from datetime import datetime, timedelta
from typing import List, Dict, Optional
import argparse
import time

# Agregar src al path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.crawlers.norm_detail_crawler_OPTIMIZED import NormDetailCrawlerOptimized


class DownloadManager:
    """Gestiona la descarga masiva de normas."""

    def __init__(self,
                 delay_seconds: int = 10,
                 checkpoint_every: int = 10,
                 output_dir: Path = None):
        """
        Args:
            delay_seconds: Segundos entre cada descarga (anti-bloqueo)
            checkpoint_every: Guardar progreso cada N normas
            output_dir: Directorio para guardar normas descargadas
        """
        self.delay = delay_seconds
        self.checkpoint_every = checkpoint_every
        self.output_dir = output_dir or Path("data/normas_completas")
        self.progress_file = Path("data/download_progress.json")

        # Estadísticas
        self.stats = {
            'total': 0,
            'descargadas': 0,
            'ya_existian': 0,
            'errores': 0,
            'tiempo_inicio': None,
            'tiempo_estimado': None
        }

    def load_normas_list(self) -> List[Dict]:
        """Cargar lista de normas a descargar."""
        normas_file = Path("data/busquedas/normas_completas.json")

        with open(normas_file, 'r', encoding='utf-8') as f:
            data = json.load(f)

        return data['normas']

    def get_output_path(self, norma: Dict) -> Path:
        """Obtener ruta de salida para una norma."""
        tipo = norma.get('tipo', 'otros').lower()
        numero = norma.get('numero', 'sin_numero')

        # Mapear tipos a carpetas
        tipo_folder = {
            'DECRETO': 'decretos',
            'LEY': 'leyes',
            'DFL': 'dfl',
            'RESOLUCION': 'resoluciones',
            'RESOLUCIÓN': 'resoluciones',
        }.get(tipo.upper(), 'otros')

        folder = self.output_dir / tipo_folder
        folder.mkdir(parents=True, exist_ok=True)

        # Nombre de archivo
        filename = f"{tipo.lower()}_{numero}.json"
        return folder / filename

    def already_downloaded(self, norma: Dict) -> bool:
        """Verificar si una norma ya fue descargada."""
        output_path = self.get_output_path(norma)

        if not output_path.exists():
            return False

        # Verificar que tenga texto_completo
        try:
            with open(output_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
                return len(data.get('texto_completo', '')) > 500
        except:
            return False

    def save_norm(self, norm_data, norma_original: Dict):
        """Guardar norma descargada."""
        if not norm_data:
            return False

        output_path = self.get_output_path(norma_original)

        try:
            # Convertir a dict si es dataclass
            if hasattr(norm_data, '__dict__'):
                from dataclasses import asdict
                data = asdict(norm_data)
            else:
                data = norm_data

            with open(output_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)

            return True
        except Exception as e:
            print(f"    ❌ Error guardando: {e}")
            return False

    def save_progress(self, processed_ids: List[str]):
        """Guardar progreso para poder resumir."""
        progress = {
            'fecha': datetime.now().isoformat(),
            'procesados': processed_ids,
            'stats': self.stats
        }

        with open(self.progress_file, 'w', encoding='utf-8') as f:
            json.dump(progress, f, indent=2, ensure_ascii=False)

    def load_progress(self) -> List[str]:
        """Cargar IDs ya procesados."""
        if not self.progress_file.exists():
            return []

        try:
            with open(self.progress_file, 'r', encoding='utf-8') as f:
                progress = json.load(f)
                return progress.get('procesados', [])
        except:
            return []

    def filter_pending(self, normas: List[Dict], resume: bool = False) -> List[Dict]:
        """Filtrar normas pendientes de descargar."""
        if resume:
            processed = set(self.load_progress())
            print(f"  📂 Resumiendo: {len(processed)} ya procesadas")
        else:
            processed = set()

        pending = []
        for norma in normas:
            id_norma = norma.get('id_norma')

            # Si está en progreso previo, skip
            if id_norma in processed:
                continue

            # Si ya existe archivo completo, skip
            if self.already_downloaded(norma):
                self.stats['ya_existian'] += 1
                continue

            pending.append(norma)

        return pending

    def get_top_normas(self, normas: List[Dict], top_n: int) -> List[Dict]:
        """Obtener las TOP N normas más importantes."""
        # Criterio: más vinculaciones = más importante
        normas_sorted = sorted(
            normas,
            key=lambda n: n.get('num_vinculaciones', 0),
            reverse=True
        )
        return normas_sorted[:top_n]

    def print_header(self, pending: List[Dict]):
        """Imprimir encabezado con información."""
        print("\n" + "=" * 70)
        print("🚀 DESCARGA MASIVA DE NORMAS BCN - TEXTO COMPLETO")
        print("=" * 70)
        print(f"\n📊 Estadísticas:")
        print(f"  Total en dataset: {self.stats['total']}")
        print(f"  Ya descargadas: {self.stats['ya_existian']}")
        print(f"  Pendientes: {len(pending)}")
        print(f"\n⚙️  Configuración:")
        print(f"  Delay entre descargas: {self.delay}s")
        print(f"  Checkpoint cada: {self.checkpoint_every} normas")
        print(f"  Directorio salida: {self.output_dir}")

    def print_progress(self, current: int, total: int, norma: Dict, success: bool):
        """Imprimir progreso de descarga."""
        porcentaje = (current / total) * 100

        # Calcular tiempo estimado
        if self.stats['tiempo_inicio']:
            elapsed = datetime.now() - self.stats['tiempo_inicio']
            avg_time = elapsed.total_seconds() / current
            remaining = (total - current) * avg_time
            eta = timedelta(seconds=int(remaining))
            eta_str = str(eta)
        else:
            eta_str = "calculando..."

        # Barra de progreso
        bar_length = 30
        filled = int(bar_length * current / total)
        bar = '█' * filled + '░' * (bar_length - filled)

        status = "✅" if success else "❌"
        tipo = norma.get('tipo', '???')
        numero = norma.get('numero', '???')

        print(f"\n[{current}/{total}] {bar} {porcentaje:.1f}%")
        print(f"  {status} {tipo} {numero}")
        print(f"  ⏱️  ETA: {eta_str}")
        print(f"  📈 Éxito: {self.stats['descargadas']} | Errores: {self.stats['errores']}")

    def print_summary(self):
        """Imprimir resumen final."""
        elapsed = datetime.now() - self.stats['tiempo_inicio']

        print("\n" + "=" * 70)
        print("✅ DESCARGA COMPLETADA")
        print("=" * 70)
        print(f"\n📊 Resumen:")
        print(f"  Total procesadas: {self.stats['descargadas'] + self.stats['errores']}")
        print(f"  ✅ Exitosas: {self.stats['descargadas']}")
        print(f"  ❌ Errores: {self.stats['errores']}")
        print(f"  📂 Ya existían: {self.stats['ya_existian']}")
        print(f"\n⏱️  Tiempo total: {elapsed}")
        print(f"\n💾 Archivos guardados en: {self.output_dir}")
        print("=" * 70)

    async def download_all(self,
                          top_n: Optional[int] = None,
                          resume: bool = False,
                          max_concurrent: int = 1):
        """
        Descargar todas las normas.

        Args:
            top_n: Solo descargar TOP N más importantes (None = todas)
            resume: Continuar desde checkpoint previo
            max_concurrent: Descargas simultáneas (1 = secuencial, más seguro)
        """
        # Cargar lista de normas
        print("\n🔍 Cargando lista de normas...")
        normas = self.load_normas_list()
        self.stats['total'] = len(normas)

        # Filtrar TOP N si se especificó
        if top_n:
            print(f"  🎯 Filtrando TOP {top_n} más importantes...")
            normas = self.get_top_normas(normas, top_n)

        # Filtrar pendientes
        pending = self.filter_pending(normas, resume=resume)

        if not pending:
            print("\n✅ No hay normas pendientes. Todas ya están descargadas!")
            return

        # Imprimir header
        self.print_header(pending)

        # Confirmar
        if not top_n and len(pending) > 100:
            print(f"\n⚠️  Vas a descargar {len(pending)} normas.")
            print(f"   Tiempo estimado: ~{(len(pending) * self.delay) / 3600:.1f} horas")
            response = input("\n¿Continuar? (y/N): ")
            if response.lower() != 'y':
                print("❌ Cancelado por usuario")
                return

        # Iniciar descarga
        self.stats['tiempo_inicio'] = datetime.now()
        processed_ids = self.load_progress() if resume else []

        print("\n" + "-" * 70)
        print("📥 INICIANDO DESCARGA...")
        print("-" * 70)

        async with NormDetailCrawlerOptimized(headless=True, validate=True) as crawler:
            for i, norma in enumerate(pending, 1):
                id_norma = norma.get('id_norma')

                try:
                    # Descargar
                    norm_data = await crawler.fetch_norm(id_norma)

                    # Guardar
                    if norm_data:
                        success = self.save_norm(norm_data, norma)
                        if success:
                            self.stats['descargadas'] += 1
                            processed_ids.append(id_norma)
                        else:
                            self.stats['errores'] += 1
                    else:
                        self.stats['errores'] += 1
                        success = False

                    # Mostrar progreso
                    self.print_progress(i, len(pending), norma, success)

                    # Checkpoint
                    if i % self.checkpoint_every == 0:
                        print("  💾 Guardando checkpoint...")
                        self.save_progress(processed_ids)

                    # Delay anti-bloqueo
                    if i < len(pending):  # No delay en el último
                        await asyncio.sleep(self.delay)

                except KeyboardInterrupt:
                    print("\n\n⚠️  Interrumpido por usuario. Guardando progreso...")
                    self.save_progress(processed_ids)
                    print(f"✅ Progreso guardado. Usa --resume para continuar.")
                    return

                except Exception as e:
                    print(f"\n  ❌ Error inesperado: {e}")
                    self.stats['errores'] += 1
                    # Continuar con la siguiente

        # Guardar progreso final
        self.save_progress(processed_ids)

        # Resumen
        self.print_summary()


async def main():
    parser = argparse.ArgumentParser(
        description='Descarga masiva de normas BCN con texto completo',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Ejemplos:
  # Descargar todas las normas
  python3 scripts/DOWNLOAD_ALL_NORMS.py

  # Solo las TOP 50 más importantes
  python3 scripts/DOWNLOAD_ALL_NORMS.py --top 50

  # Continuar descarga interrumpida
  python3 scripts/DOWNLOAD_ALL_NORMS.py --resume

  # Modo rápido (15s delay, más riesgo)
  python3 scripts/DOWNLOAD_ALL_NORMS.py --fast

  # Ejecutar en background
  nohup python3 scripts/DOWNLOAD_ALL_NORMS.py &> download.log &
  tail -f download.log  # Ver progreso
        """
    )

    parser.add_argument('--top', type=int,
                       help='Descargar solo TOP N normas más importantes')
    parser.add_argument('--resume', action='store_true',
                       help='Continuar desde checkpoint anterior')
    parser.add_argument('--fast', action='store_true',
                       help='Modo rápido (5s delay en lugar de 10s)')
    parser.add_argument('--delay', type=int, default=None,
                       help='Delay personalizado en segundos (default: 10)')

    args = parser.parse_args()

    # Configurar delay
    if args.delay:
        delay = args.delay
    elif args.fast:
        delay = 5
    else:
        delay = 10

    # Crear manager y ejecutar
    manager = DownloadManager(delay_seconds=delay)
    await manager.download_all(
        top_n=args.top,
        resume=args.resume
    )


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n\n⚠️  Interrumpido. Usa --resume para continuar.")
        sys.exit(1)
