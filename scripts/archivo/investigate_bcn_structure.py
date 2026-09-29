#!/usr/bin/env python3
"""
Script para investigar la estructura de BCN y qué información de relaciones está disponible.
Objetivo: Determinar si necesitamos OCR/PDF o si basta con mejor scraping web.
"""

import asyncio
from playwright.async_api import async_playwright
from playwright_stealth import Stealth


async def investigate_bcn_page(id_norma: str = "250604"):
    """
    Investigar la estructura de una página BCN.
    - ¿Qué tabs/pestañas existen?
    - ¿Hay una sección de Vinculaciones?
    - ¿Qué información estructurada hay disponible?
    """
    url = f"https://www.bcn.cl/leychile/navegar?idNorma={id_norma}"

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)  # headless=False para ver
        context = await browser.new_context()
        stealth = Stealth()
        await stealth.apply_stealth_async(context)

        page = await context.new_page()

        print(f"=" * 70)
        print(f"INVESTIGANDO: {url}")
        print(f"=" * 70)

        await page.goto(url, wait_until='networkidle', timeout=60000)
        await asyncio.sleep(5)  # Esperar carga completa

        # 1. Buscar tabs/pestañas
        print("\n1. TABS/PESTAÑAS ENCONTRADAS:")
        tabs = await page.evaluate('''() => {
            const tabs = [];
            // Buscar elementos que parezcan tabs
            const tabElements = document.querySelectorAll('[role="tab"], .nav-tabs li, .tab, button[data-toggle="tab"], a[data-toggle="tab"]');
            tabElements.forEach(t => tabs.push({text: t.innerText, class: t.className, id: t.id}));

            // También buscar links que parezcan navegación
            const navLinks = document.querySelectorAll('.nav a, .tabs a, [class*="tab"] a');
            navLinks.forEach(t => tabs.push({text: t.innerText, href: t.href, class: t.className}));

            return tabs;
        }''')
        for tab in tabs:
            print(f"   - {tab}")

        # 2. Buscar sección de vinculaciones
        print("\n2. BUSCANDO 'VINCULACIONES' EN LA PÁGINA:")
        vinculaciones_search = await page.evaluate('''() => {
            const results = [];
            const body = document.body.innerText;

            // Buscar menciones de vinculaciones
            const lines = body.split('\\n');
            for (let i = 0; i < lines.length; i++) {
                const line = lines[i].toLowerCase();
                if (line.includes('vinculac') || line.includes('modifica') ||
                    line.includes('deroga') || line.includes('relacionad')) {
                    results.push({line_num: i, text: lines[i].substring(0, 150)});
                }
            }
            return results.slice(0, 20);  // Limitar resultados
        }''')
        for r in vinculaciones_search:
            print(f"   Línea {r['line_num']}: {r['text']}")

        # 3. Buscar links a otras normas
        print("\n3. LINKS A OTRAS NORMAS (idNorma):")
        norm_links = await page.evaluate('''() => {
            const links = [];
            document.querySelectorAll('a[href*="idNorma"]').forEach(a => {
                links.push({
                    text: a.innerText.substring(0, 100),
                    href: a.href,
                    parent: a.parentElement?.innerText?.substring(0, 50)
                });
            });
            return links.slice(0, 15);
        }''')
        for link in norm_links:
            print(f"   - {link['text'][:50]} -> {link['href']}")

        # 4. Buscar metadata estructurada
        print("\n4. METADATA ESTRUCTURADA (elementos con 'metadata', 'info', etc.):")
        metadata = await page.evaluate('''() => {
            const meta = [];
            const selectors = [
                '[class*="metadata"]', '[class*="info-"]', '[class*="detalle"]',
                'dl', '.ficha', '[class*="ficha"]', '[class*="datos"]'
            ];
            selectors.forEach(sel => {
                document.querySelectorAll(sel).forEach(el => {
                    if (el.innerText.length > 10 && el.innerText.length < 500) {
                        meta.push({selector: sel, text: el.innerText.substring(0, 200)});
                    }
                });
            });
            return meta.slice(0, 10);
        }''')
        for m in metadata:
            print(f"   [{m['selector']}]: {m['text'][:100]}...")

        # 5. Intentar hacer click en tab de Vinculaciones si existe
        print("\n5. INTENTANDO ENCONTRAR Y CLICK EN 'VINCULACIONES':")
        vinc_tab_clicked = await page.evaluate('''() => {
            // Buscar cualquier elemento clickeable con "vinculaciones"
            const elements = Array.from(document.querySelectorAll('*'));
            for (const el of elements) {
                if (el.innerText.toLowerCase().includes('vinculaciones') &&
                    (el.tagName === 'A' || el.tagName === 'BUTTON' ||
                     el.onclick || el.getAttribute('data-toggle'))) {
                    return {found: true, text: el.innerText, tag: el.tagName};
                }
            }
            return {found: false};
        }''')
        print(f"   Resultado: {vinc_tab_clicked}")

        # Si encontró, intentar click
        if vinc_tab_clicked.get('found'):
            try:
                await page.click('text=Vinculaciones', timeout=5000)
                await asyncio.sleep(3)
                print("   ✓ Click exitoso en Vinculaciones")

                # Extraer contenido después del click
                vinc_content = await page.evaluate('''() => {
                    return document.body.innerText.substring(0, 5000);
                }''')
                print("\n   CONTENIDO DESPUÉS DE CLICK:")
                print(vinc_content[:2000])
            except:
                print("   ✗ No se pudo hacer click")

        # 6. Buscar API calls en la red
        print("\n6. ESTRUCTURA HTML PRINCIPAL:")
        html_structure = await page.evaluate('''() => {
            const main = document.querySelector('main, #main, .main, [role="main"]');
            if (main) {
                return main.innerHTML.substring(0, 1000);
            }
            return document.body.innerHTML.substring(0, 1000);
        }''')
        print(f"   {html_structure[:500]}...")

        # 7. Verificar si hay PDFs
        print("\n7. LINKS A PDFs:")
        pdf_links = await page.evaluate('''() => {
            const pdfs = [];
            document.querySelectorAll('a[href*=".pdf"], a[href*="pdf"]').forEach(a => {
                pdfs.push({text: a.innerText, href: a.href});
            });
            return pdfs;
        }''')
        for pdf in pdf_links:
            print(f"   - {pdf['text']} -> {pdf['href']}")

        # Esperar para observar
        print("\n" + "=" * 70)
        print("Browser abierto. Presiona Ctrl+C para cerrar.")
        print("=" * 70)

        try:
            await asyncio.sleep(60)  # Mantener abierto para observar
        except:
            pass

        await browser.close()


if __name__ == "__main__":
    asyncio.run(investigate_bcn_page())
