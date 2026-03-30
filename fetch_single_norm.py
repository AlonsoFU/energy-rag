#!/usr/bin/env python3
"""Re-descarga una norma específica con wait extendido para contenido largo."""

import asyncio
import json
import hashlib
import sys
from pathlib import Path
from datetime import datetime

from playwright.async_api import async_playwright
from playwright_stealth import Stealth


async def fetch_norm_full(id_norma: str, output_dir: Path):
    """Descarga una norma con espera extendida para contenido dinámico."""
    url = f"https://www.bcn.cl/leychile/navegar?idNorma={id_norma}"
    print(f"Descargando: {url}")

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            viewport={"width": 1280, "height": 800},
            user_agent="Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36"
        )
        await Stealth().apply_stealth_async(context)
        page = await context.new_page()

        # Estrategia 1: networkidle con timeout largo
        print("  Estrategia 1: networkidle (90s timeout)...")
        try:
            await page.goto(url, wait_until='networkidle', timeout=90000)
            await page.wait_for_timeout(5000)  # 5s extra para lazy load
        except Exception as e:
            print(f"  Timeout networkidle, intentando scroll...")

        # Scroll para forzar lazy loading
        print("  Scrolling para cargar contenido dinámico...")
        for i in range(20):
            await page.evaluate(f"window.scrollTo(0, {(i+1) * 2000})")
            await page.wait_for_timeout(500)

        # Volver arriba y esperar
        await page.evaluate("window.scrollTo(0, 0)")
        await page.wait_for_timeout(2000)

        # Extraer texto
        texto = await page.evaluate("""() => {
            // Buscar el contenedor principal
            const selectors = ['.cuerpo-norma', '#texto-norma', 'article', '.contenido'];
            for (const sel of selectors) {
                const el = document.querySelector(sel);
                if (el && el.innerText.length > 500) return el.innerText;
            }
            return document.body.innerText;
        }""")

        # Extraer título
        titulo = await page.evaluate("""() => {
            const el = document.querySelector('h1, .titulo-norma, [class*="titulo"]');
            return el ? el.innerText.trim() : '';
        }""")

        # Extraer metadata del texto
        import re
        tipo = ''
        numero = ''
        if titulo:
            m = re.match(r'(DECRETO|LEY|DFL|RESOLUCIÓN)\s+(\d+)', titulo.upper())
            if m:
                tipo, numero = m.group(1), m.group(2)

        await browser.close()

    print(f"  Texto extraído: {len(texto)} caracteres")

    # Buscar cuántos artículos hay
    import re
    articulos = re.findall(r'Artículo\s+\d+', texto)
    print(f"  Artículos detectados: {len(articulos)}")

    if len(texto) < 1000:
        print(f"  ⚠️  Texto muy corto ({len(texto)} chars), puede estar incompleto")

    # Guardar
    data = {
        "id_norma": id_norma,
        "tipo": tipo or "DECRETO",
        "numero": numero or id_norma,
        "titulo": titulo,
        "fecha_publicacion": "",
        "fecha_promulgacion": None,
        "organismo": "",
        "estado": "DESCONOCIDO",
        "url": url,
        "texto_completo": texto,
        "content_hash": hashlib.sha256(texto.encode()).hexdigest()[:16],
        "vinculaciones": {"modifica_a": [], "modificada_por": [], "deroga_a": [],
                         "derogada_por": [], "reglamenta": [], "reglamentada_por": [],
                         "referencias": []},
        "versiones": [],
        "extracted_at": datetime.now().isoformat(),
    }

    # Determinar filename
    output_dir.mkdir(parents=True, exist_ok=True)
    filename = output_dir / f"decreto_{numero or id_norma}.json"

    # Backup del archivo anterior si existe
    if filename.exists():
        backup = filename.with_suffix('.json.bak')
        filename.rename(backup)
        print(f"  Backup: {backup}")

    with open(filename, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

    print(f"  ✅ Guardado: {filename}")
    return data


if __name__ == "__main__":
    id_norma = sys.argv[1] if len(sys.argv) > 1 else "1146553"
    output_dir = Path("data/normas_completas/decretos")
    asyncio.run(fetch_norm_full(id_norma, output_dir))
