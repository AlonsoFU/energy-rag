#!/usr/bin/env python3
"""
Reintentar descarga de normas que fallaron.

Estrategias:
1. Timeout más largo (60s)
2. Espera adicional después de cargar
3. Si falla: requests directo (sin JavaScript)
"""

import asyncio
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.crawlers.norm_detail_crawler_OPTIMIZED import NormDetailCrawlerOptimized
from playwright.async_api import async_playwright
from playwright_stealth import Stealth
import requests


def get_output_path(id_norma: str, tipo: str, numero: str) -> Path:
    """Obtener ruta donde se guarda una norma."""
    base = Path("data/normas_completas")

    tipo_folder = {
        'DECRETO': 'decretos',
        'LEY': 'leyes',
        'DFL': 'dfl',
        'RESOLUCION': 'resoluciones',
        'RESOLUCIÓN': 'resoluciones',
    }.get(tipo.upper() if tipo else '', 'otros')

    folder = base / tipo_folder
    folder.mkdir(parents=True, exist_ok=True)

    filename = f"{tipo.lower() if tipo else 'norma'}_{numero if numero else id_norma}.json"
    return folder / filename


async def retry_with_long_timeout(id_norma: str, nombre: str):
    """
    ESTRATEGIA 1: Reintentar con timeout largo y espera adicional.
    """
    print(f"\n{'='*70}")
    print(f"🔄 ESTRATEGIA 1: Timeout largo (60s)")
    print(f"{'='*70}")
    print(f"📥 {nombre} (ID: {id_norma})")

    playwright = await async_playwright().start()
    browser = await playwright.chromium.launch(headless=True)
    context = await browser.new_context()
    stealth = Stealth()
    await stealth.apply_stealth_async(context)
    page = await context.new_page()

    url = f"https://www.bcn.cl/leychile/navegar?idNorma={id_norma}"

    try:
        print(f"  🌐 Accediendo: {url}")

        # ESTRATEGIA: Timeout MÁS LARGO
        await page.goto(url, wait_until='domcontentloaded', timeout=60000)  # 60s

        # ESPERA ADICIONAL para contenido dinámico
        print(f"  ⏱️  Esperando contenido dinámico...")
        await asyncio.sleep(10)  # 10s extra

        # Intentar forzar scroll (a veces carga más contenido)
        await page.evaluate('window.scrollTo(0, document.body.scrollHeight)')
        await asyncio.sleep(2)

        # Extraer texto
        texto = await page.evaluate('''() => {
            return document.body.innerText || '';
        }''')

        if len(texto) > 500:
            print(f"  ✅ ÉXITO: {len(texto)} caracteres")
            await browser.close()
            await playwright.stop()
            return texto
        else:
            print(f"  ❌ Texto muy corto: {len(texto)} chars")
            await browser.close()
            await playwright.stop()
            return None

    except Exception as e:
        print(f"  ❌ Error: {e}")
        await browser.close()
        await playwright.stop()
        return None


async def retry_with_networkidle(id_norma: str, nombre: str):
    """
    ESTRATEGIA 2: Esperar a que NO haya actividad de red.
    """
    print(f"\n{'='*70}")
    print(f"🔄 ESTRATEGIA 2: Wait until networkidle")
    print(f"{'='*70}")
    print(f"📥 {nombre} (ID: {id_norma})")

    playwright = await async_playwright().start()
    browser = await playwright.chromium.launch(headless=True)
    context = await browser.new_context()
    stealth = Stealth()
    await stealth.apply_stealth_async(context)
    page = await context.new_page()

    url = f"https://www.bcn.cl/leychile/navegar?idNorma={id_norma}"

    try:
        print(f"  🌐 Accediendo: {url}")

        # ESTRATEGIA: Esperar networkidle (más lento pero más completo)
        await page.goto(url, wait_until='networkidle', timeout=90000)  # 90s

        print(f"  ⏱️  Esperando 5s adicionales...")
        await asyncio.sleep(5)

        # Extraer texto
        texto = await page.evaluate('''() => {
            return document.body.innerText || '';
        }''')

        if len(texto) > 500:
            print(f"  ✅ ÉXITO: {len(texto)} caracteres")
            await browser.close()
            await playwright.stop()
            return texto
        else:
            print(f"  ❌ Texto muy corto: {len(texto)} chars")
            await browser.close()
            await playwright.stop()
            return None

    except Exception as e:
        print(f"  ❌ Error: {e}")
        await browser.close()
        await playwright.stop()
        return None


def retry_with_requests(id_norma: str, nombre: str):
    """
    ESTRATEGIA 3: Requests directo (sin JavaScript).

    Si BCN sirve contenido sin JS, esto es más rápido y confiable.
    """
    print(f"\n{'='*70}")
    print(f"🔄 ESTRATEGIA 3: Requests directo (sin JS)")
    print(f"{'='*70}")
    print(f"📥 {nombre} (ID: {id_norma})")

    url = f"https://www.bcn.cl/leychile/navegar?idNorma={id_norma}"

    try:
        print(f"  🌐 Accediendo: {url}")

        headers = {
            'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Accept-Language': 'es-CL,es;q=0.9,en;q=0.8',
        }

        response = requests.get(url, headers=headers, timeout=30)

        if response.status_code == 200:
            # Extraer texto del HTML
            from bs4 import BeautifulSoup
            soup = BeautifulSoup(response.text, 'html.parser')

            # Remover scripts y styles
            for script in soup(['script', 'style', 'nav', 'header', 'footer']):
                script.decompose()

            texto = soup.get_text(separator='\n', strip=True)

            if len(texto) > 500:
                print(f"  ✅ ÉXITO: {len(texto)} caracteres")
                return texto
            else:
                print(f"  ❌ Texto muy corto: {len(texto)} chars")
                return None
        else:
            print(f"  ❌ Status code: {response.status_code}")
            return None

    except Exception as e:
        print(f"  ❌ Error: {e}")
        return None


async def download_and_save(id_norma: str, tipo: str, numero: str, nombre: str):
    """Intentar descargar con múltiples estrategias."""
    print(f"\n{'#'*70}")
    print(f"PROCESANDO: {nombre}")
    print(f"ID: {id_norma} | Tipo: {tipo or 'DESCONOCIDO'} | Número: {numero or 'N/A'}")
    print(f"{'#'*70}")

    texto = None
    estrategia_exitosa = None

    # ESTRATEGIA 1: Timeout largo
    texto = await retry_with_long_timeout(id_norma, nombre)
    if texto:
        estrategia_exitosa = "Timeout largo (60s)"

    # ESTRATEGIA 2: Network idle
    if not texto:
        texto = await retry_with_networkidle(id_norma, nombre)
        if texto:
            estrategia_exitosa = "Network idle"

    # ESTRATEGIA 3: Requests directo
    if not texto:
        texto = retry_with_requests(id_norma, nombre)
        if texto:
            estrategia_exitosa = "Requests directo"

    # Guardar si tuvo éxito
    if texto:
        print(f"\n✅ ÉXITO con estrategia: {estrategia_exitosa}")

        # Crear estructura mínima
        data = {
            'id_norma': id_norma,
            'tipo': tipo or '',
            'numero': numero or '',
            'titulo': nombre,
            'texto_completo': texto,
            'url': f"https://www.bcn.cl/leychile/navegar?idNorma={id_norma}",
            'extracted_at': time.strftime('%Y-%m-%dT%H:%M:%S'),
            'estrategia': estrategia_exitosa
        }

        output_path = get_output_path(id_norma, tipo, numero)

        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

        print(f"💾 Guardado: {output_path}")
        return True
    else:
        print(f"\n❌ FALLO con todas las estrategias")
        return False


async def main():
    print("=" * 70)
    print("🔄 REINTENTO DE NORMAS FALLIDAS")
    print("=" * 70)

    # Las 4 normas que fallaron
    failed_norms = [
        {
            'id_norma': '1047565',
            'tipo': 'DECRETO',
            'numero': '130',
            'nombre': 'Decreto 130'
        },
        {
            'id_norma': '1099982',
            'tipo': 'LEY',
            'numero': '20999',
            'nombre': 'Ley 20999'
        },
        {
            'id_norma': '1187684',
            'tipo': 'LEY',
            'numero': '21527',
            'nombre': 'Ley 21527'
        },
        {
            'id_norma': '1199483',
            'tipo': 'LEY',
            'numero': '21647',
            'nombre': 'Ley 21647'
        },
    ]

    print(f"\n📊 Total a reintentar: {len(failed_norms)}")
    print("\nEstrategias que se probarán:")
    print("  1️⃣  Timeout largo (60s) + espera adicional")
    print("  2️⃣  Wait until networkidle (90s)")
    print("  3️⃣  Requests directo sin JavaScript")
    print()

    response = input("¿Continuar? (y/N): ")
    if response.lower() != 'y':
        print("❌ Cancelado")
        return

    # Procesar cada norma
    stats = {'éxitos': 0, 'fallos': 0}

    for i, norma in enumerate(failed_norms, 1):
        print(f"\n{'='*70}")
        print(f"NORMA {i}/{len(failed_norms)}")
        print(f"{'='*70}")

        success = await download_and_save(
            norma['id_norma'],
            norma['tipo'],
            norma['numero'],
            norma['nombre']
        )

        if success:
            stats['éxitos'] += 1
        else:
            stats['fallos'] += 1

        # Delay entre normas
        if i < len(failed_norms):
            print(f"\n⏱️  Esperando 15s antes de siguiente norma...")
            await asyncio.sleep(15)

    # Resumen final
    print("\n" + "=" * 70)
    print("✅ PROCESO COMPLETADO")
    print("=" * 70)
    print(f"\n📊 Resultados:")
    print(f"  ✅ Éxitos: {stats['éxitos']}/4")
    print(f"  ❌ Fallos: {stats['fallos']}/4")

    if stats['éxitos'] > 0:
        print(f"\n💾 Archivos guardados en: data/normas_completas/")

    if stats['fallos'] > 0:
        print(f"\n⚠️  {stats['fallos']} normas aún no se pudieron descargar")
        print("     Posibles razones:")
        print("     - BCN no tiene el contenido disponible")
        print("     - Requiere autenticación")
        print("     - URL incorrecta")


if __name__ == "__main__":
    asyncio.run(main())
