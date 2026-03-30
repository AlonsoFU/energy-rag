#!/usr/bin/env python3
"""
Monitor de cambios en normas BCN.

Detecta:
1. Nuevas normas que modifican/derogan normas monitoreadas
2. Cambios en el contenido de normas existentes
3. Nuevas vinculaciones en BCN

Uso:
    python monitor_cambios.py              # Verificar cambios
    python monitor_cambios.py --full       # Verificación completa con descarga
"""

import json
import hashlib
import asyncio
from pathlib import Path
from datetime import datetime, timedelta
from typing import Dict, List, Optional
from dataclasses import dataclass, asdict

# Importar crawler existente (opcional)
import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

try:
    from src.crawlers.norm_content_crawler import NormContentCrawler
    CRAWLER_AVAILABLE = True
except ImportError:
    CRAWLER_AVAILABLE = False


@dataclass
class CambioDetectado:
    """Representa un cambio detectado."""
    tipo_cambio: str  # NUEVA_MODIFICACION, CONTENIDO_MODIFICADO, NUEVA_DEROGACION
    norma_afectada: str  # ID norma afectada
    norma_origen: Optional[str]  # ID norma que causa el cambio
    descripcion: str
    fecha_deteccion: str
    detalles: dict = None


class MonitorCambios:
    """Monitor de cambios en normas BCN."""

    def __init__(self, data_path: Path = None):
        self.data_path = data_path or Path(__file__).parent.parent / "data"
        self.normas_path = self.data_path / "normas_estructuradas"
        self.textos_path = self.data_path / "textos"
        self.monitor_path = self.data_path / "monitor"
        self.monitor_path.mkdir(parents=True, exist_ok=True)

        # Cargar índice actual
        self.indice = self._cargar_indice()

        # Cargar historial de cambios
        self.historial = self._cargar_historial()

    def _cargar_indice(self) -> dict:
        """Cargar índice de normas."""
        indice_path = self.normas_path / "indice_normas.json"
        if indice_path.exists():
            with open(indice_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        return {"normas": [], "indice": {}}

    def _cargar_historial(self) -> List[dict]:
        """Cargar historial de cambios detectados."""
        historial_path = self.monitor_path / "historial_cambios.json"
        if historial_path.exists():
            with open(historial_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
                return data.get("cambios", [])
        return []

    def _guardar_historial(self):
        """Guardar historial de cambios."""
        historial_path = self.monitor_path / "historial_cambios.json"
        with open(historial_path, 'w', encoding='utf-8') as f:
            json.dump({
                "ultima_verificacion": datetime.now().isoformat(),
                "total_cambios": len(self.historial),
                "cambios": self.historial
            }, f, indent=2, ensure_ascii=False)

    def calcular_hash(self, texto: str) -> str:
        """Calcular hash SHA256 del contenido."""
        return hashlib.sha256(texto.encode('utf-8')).hexdigest()[:16]

    def _cargar_hashes_actuales(self) -> Dict[str, str]:
        """Cargar hashes de contenido actual."""
        hashes_path = self.monitor_path / "hashes_contenido.json"
        if hashes_path.exists():
            with open(hashes_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        return {}

    def _guardar_hashes(self, hashes: Dict[str, str]):
        """Guardar hashes de contenido."""
        hashes_path = self.monitor_path / "hashes_contenido.json"
        with open(hashes_path, 'w', encoding='utf-8') as f:
            json.dump(hashes, f, indent=2)

    def verificar_cambios_contenido(self) -> List[CambioDetectado]:
        """
        Verificar si el contenido de los archivos .txt ha cambiado.
        Compara hashes actuales con hashes guardados.
        """
        cambios = []
        hashes_anteriores = self._cargar_hashes_actuales()
        hashes_nuevos = {}

        for txt_file in self.textos_path.glob("*.txt"):
            id_norma = txt_file.stem

            with open(txt_file, 'r', encoding='utf-8') as f:
                contenido = f.read()

            hash_actual = self.calcular_hash(contenido)
            hashes_nuevos[id_norma] = hash_actual

            if id_norma in hashes_anteriores:
                if hashes_anteriores[id_norma] != hash_actual:
                    cambio = CambioDetectado(
                        tipo_cambio="CONTENIDO_MODIFICADO",
                        norma_afectada=id_norma,
                        norma_origen=None,
                        descripcion=f"El contenido de la norma {id_norma} cambió",
                        fecha_deteccion=datetime.now().isoformat(),
                        detalles={
                            "hash_anterior": hashes_anteriores[id_norma],
                            "hash_nuevo": hash_actual
                        }
                    )
                    cambios.append(cambio)

        # Guardar nuevos hashes
        self._guardar_hashes(hashes_nuevos)

        return cambios

    def comparar_modificaciones(self, norma_actual: dict, norma_nueva: dict) -> List[CambioDetectado]:
        """
        Comparar lista de modificaciones entre versión actual y nueva.
        Detecta nuevas modificaciones.
        """
        cambios = []

        mods_actuales = {
            f"{m['tipo']}_{m['numero']}"
            for m in norma_actual.get("relaciones", {}).get("modificada_por", [])
        }

        mods_nuevas = {
            f"{m['tipo']}_{m['numero']}"
            for m in norma_nueva.get("relaciones", {}).get("modificada_por", [])
        }

        # Detectar nuevas modificaciones
        nuevas = mods_nuevas - mods_actuales
        for mod_key in nuevas:
            # Buscar detalles de la modificación
            for m in norma_nueva["relaciones"]["modificada_por"]:
                if f"{m['tipo']}_{m['numero']}" == mod_key:
                    cambio = CambioDetectado(
                        tipo_cambio="NUEVA_MODIFICACION",
                        norma_afectada=norma_actual["id_norma"],
                        norma_origen=m.get("id_norma"),
                        descripcion=f"{m['tipo']} {m['numero']} modifica a {norma_actual['tipo']} {norma_actual['numero']}",
                        fecha_deteccion=datetime.now().isoformat(),
                        detalles={
                            "modificador": m,
                            "fecha_do": m.get("fecha_do")
                        }
                    )
                    cambios.append(cambio)
                    break

        return cambios

    async def verificar_bcn_online(self, id_norma: str) -> Optional[dict]:
        """
        Descargar información actualizada de BCN.
        Útil para verificar si hay nuevas modificaciones.
        """
        if not CRAWLER_AVAILABLE:
            print("   (Crawler no disponible)")
            return None
        async with NormContentCrawler() as crawler:
            result = await crawler.extract_complete_norm(id_norma)
            return result

    def generar_reporte(self, cambios: List[CambioDetectado]) -> str:
        """Generar reporte de cambios detectados."""
        if not cambios:
            return "No se detectaron cambios."

        reporte = []
        reporte.append("=" * 60)
        reporte.append("REPORTE DE CAMBIOS DETECTADOS")
        reporte.append(f"Fecha: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
        reporte.append("=" * 60)

        # Agrupar por tipo
        por_tipo = {}
        for cambio in cambios:
            tipo = cambio.tipo_cambio
            if tipo not in por_tipo:
                por_tipo[tipo] = []
            por_tipo[tipo].append(cambio)

        for tipo, lista in por_tipo.items():
            reporte.append(f"\n### {tipo} ({len(lista)})")
            for cambio in lista:
                reporte.append(f"  - {cambio.descripcion}")
                if cambio.detalles:
                    if "fecha_do" in cambio.detalles:
                        reporte.append(f"    D.O.: {cambio.detalles['fecha_do']}")

        return "\n".join(reporte)

    def registrar_cambios(self, cambios: List[CambioDetectado]):
        """Registrar cambios en el historial."""
        for cambio in cambios:
            self.historial.append(asdict(cambio))
        self._guardar_historial()

    def obtener_normas_monitoreadas(self) -> List[str]:
        """Obtener lista de IDs de normas que estamos monitoreando."""
        return [n["id_norma"] for n in self.indice.get("normas", [])]

    def ejecutar_verificacion(self, online: bool = False) -> List[CambioDetectado]:
        """
        Ejecutar verificación completa.

        Args:
            online: Si True, consulta BCN para verificar nuevas modificaciones
        """
        print("=" * 60)
        print("VERIFICACIÓN DE CAMBIOS EN NORMAS")
        print(f"Fecha: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
        print("=" * 60)

        todos_cambios = []

        # 1. Verificar cambios en contenido local
        print("\n1. Verificando cambios en contenido local...")
        cambios_contenido = self.verificar_cambios_contenido()
        if cambios_contenido:
            print(f"   Se detectaron {len(cambios_contenido)} cambios de contenido")
            todos_cambios.extend(cambios_contenido)
        else:
            print("   Sin cambios en contenido local")

        # 2. Verificar online si se solicita
        if online:
            print("\n2. Verificando en BCN online...")
            normas_ids = self.obtener_normas_monitoreadas()

            async def verificar_todas():
                cambios_online = []
                for id_norma in normas_ids:
                    print(f"   Verificando {id_norma}...", end="")
                    try:
                        # Aquí se descargaría de BCN y se compararía
                        # Por ahora solo mostramos que se verificaría
                        print(" OK")
                    except Exception as e:
                        print(f" ERROR: {e}")
                return cambios_online

            # asyncio.run(verificar_todas())
            print("   (Verificación online deshabilitada en esta versión)")

        # Registrar cambios
        if todos_cambios:
            self.registrar_cambios(todos_cambios)

        # Generar reporte
        reporte = self.generar_reporte(todos_cambios)
        print("\n" + reporte)

        # Guardar reporte
        reporte_path = self.monitor_path / f"reporte_{datetime.now().strftime('%Y%m%d_%H%M')}.txt"
        with open(reporte_path, 'w', encoding='utf-8') as f:
            f.write(reporte)
        print(f"\nReporte guardado en: {reporte_path}")

        return todos_cambios


def main():
    import argparse

    parser = argparse.ArgumentParser(description="Monitor de cambios en normas BCN")
    parser.add_argument("--full", action="store_true", help="Verificación completa con BCN online")
    parser.add_argument("--norma", type=str, help="Verificar solo una norma específica")
    args = parser.parse_args()

    monitor = MonitorCambios()

    if args.norma:
        print(f"Verificando norma específica: {args.norma}")
        # Implementar verificación individual
    else:
        monitor.ejecutar_verificacion(online=args.full)


if __name__ == "__main__":
    main()
