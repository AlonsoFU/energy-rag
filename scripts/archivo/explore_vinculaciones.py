#!/usr/bin/env python3
"""
Explorar la estructura HTML de la sección Vinculaciones en BCN.
"""

import asyncio
from playwright.async_api import async_playwright
from playwright_stealth import Stealth


async def explore_vinculaciones(id_norma: str = "250604"):
    """Explorar estructura de Vinculaciones para una norma."""

    print(f"=" * 70)
    print(f"EXPLORANDO VINCULACIONES DE NORMA {id_norma}")
    print(f"=" * 70)

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context()
        stealth = Stealth()
        await stealth.apply_stealth_async(context)

        page = await context.new_page()

        url = f"https://www.bcn.cl/leychile/navegar?idNorma={id_norma}"
        print(f"\nAccediendo a: {url}")

        await page.goto(url, wait_until='networkidle', timeout=60000)
        await asyncio.sleep(3)

        # Buscar elementos que contengan "vinculacion" o "modifica"
        print("\n" + "-" * 70)
        print("BUSCANDO ELEMENTOS CON 'VINCULACION' O 'MODIFICA'")
        print("-" * 70)

        elements_info = await page.evaluate('''() => {
            const results = [];

            // Buscar por clases que contengan vinculacion
            const byClass = document.querySelectorAll('[class*="vincula"], [class*="relacion"], [class*="modifica"]');
            for (const el of byClass) {
                results.push({
                    type: 'by_class',
                    tag: el.tagName,
                    class: el.className,
                    id: el.id,
                    text: el.innerText.substring(0, 200)
                });
            }

            // Buscar por ID
            const byId = document.querySelectorAll('[id*="vincula"], [id*="relacion"], [id*="modifica"]');
            for (const el of byId) {
                results.push({
                    type: 'by_id',
                    tag: el.tagName,
                    class: el.className,
                    id: el.id,
                    text: el.innerText.substring(0, 200)
                });
            }

            // Buscar encabezados que digan "Vinculaciones" o "Modificaciones"
            const headers = document.querySelectorAll('h1, h2, h3, h4, h5, h6, .titulo, [class*="header"], [class*="title"]');
            for (const h of headers) {
                const text = h.innerText.toLowerCase();
                if (text.includes('vincula') || text.includes('modifica') || text.includes('relacion')) {
                    results.push({
                        type: 'header',
                        tag: h.tagName,
                        class: h.className,
                        id: h.id,
                        text: h.innerText,
                        parentClass: h.parentElement ? h.parentElement.className : null
                    });
                }
            }

            // Buscar tabs o acordeones
            const tabs = document.querySelectorAll('[role="tab"], .tab, [class*="accordion"], [class*="collapse"]');
            for (const tab of tabs) {
                const text = tab.innerText.toLowerCase();
                if (text.includes('vincula') || text.includes('modifica') || text.includes('histor')) {
                    results.push({
                        type: 'tab/accordion',
                        tag: tab.tagName,
                        class: tab.className,
                        id: tab.id,
                        text: tab.innerText.substring(0, 100)
                    });
                }
            }

            return results;
        }''')

        for el in elements_info:
            print(f"\n[{el['type']}] <{el['tag']}>")
            if el.get('id'):
                print(f"  id: {el['id']}")
            if el.get('class'):
                print(f"  class: {el['class']}")
            print(f"  text: {el['text'][:100]}...")

        # Buscar la estructura del sidebar/panel derecho
        print("\n" + "-" * 70)
        print("EXPLORANDO SIDEBAR/PANEL DERECHO")
        print("-" * 70)

        sidebar_info = await page.evaluate('''() => {
            const results = [];

            // Buscar elementos típicos de sidebar
            const sidebars = document.querySelectorAll(
                'aside, [class*="sidebar"], [class*="panel"], [class*="aside"], ' +
                '[class*="derech"], [class*="right"], [class*="lateral"], ' +
                '[class*="info-norma"], [class*="metadata"]'
            );

            for (const sb of sidebars) {
                results.push({
                    tag: sb.tagName,
                    class: sb.className,
                    id: sb.id,
                    childCount: sb.children.length,
                    text: sb.innerText.substring(0, 500)
                });
            }

            return results;
        }''')

        for sb in sidebar_info[:5]:  # Limitar a 5
            print(f"\n<{sb['tag']}> ({sb['childCount']} hijos)")
            if sb.get('id'):
                print(f"  id: {sb['id']}")
            if sb.get('class'):
                print(f"  class: {sb['class']}")
            print(f"  text preview: {sb['text'][:200]}...")

        # Buscar específicamente "Modificada por" o similar
        print("\n" + "-" * 70)
        print("BUSCANDO TEXTO 'MODIFICADA POR' EN LA PÁGINA")
        print("-" * 70)

        mod_sections = await page.evaluate('''() => {
            const results = [];
            const walker = document.createTreeWalker(
                document.body,
                NodeFilter.SHOW_TEXT,
                null,
                false
            );

            let node;
            while (node = walker.nextNode()) {
                const text = node.textContent.trim().toLowerCase();
                if (text.includes('modificada por') ||
                    text.includes('modifica a') ||
                    text.includes('deroga') ||
                    text.includes('vinculacion')) {

                    const parent = node.parentElement;
                    if (parent) {
                        // Buscar el contenedor padre más cercano con contenido relevante
                        let container = parent;
                        for (let i = 0; i < 5; i++) {
                            if (container.parentElement &&
                                container.parentElement.tagName !== 'BODY') {
                                container = container.parentElement;
                            }
                        }

                        results.push({
                            matchedText: node.textContent.trim().substring(0, 50),
                            parentTag: parent.tagName,
                            parentClass: parent.className,
                            containerTag: container.tagName,
                            containerClass: container.className,
                            containerText: container.innerText.substring(0, 300)
                        });
                    }
                }
            }

            return results.slice(0, 10);  // Limitar resultados
        }''')

        for ms in mod_sections:
            print(f"\n  Match: '{ms['matchedText']}'")
            print(f"  Parent: <{ms['parentTag']}> class='{ms['parentClass']}'")
            print(f"  Container: <{ms['containerTag']}> class='{ms['containerClass']}'")
            print(f"  Content: {ms['containerText'][:150]}...")

        # Guardar HTML para análisis manual
        print("\n" + "-" * 70)
        print("GUARDANDO HTML PARA ANÁLISIS")
        print("-" * 70)

        html = await page.content()
        from pathlib import Path
        html_path = Path(__file__).parent.parent / "data" / "debug" / f"bcn_{id_norma}.html"
        html_path.parent.mkdir(parents=True, exist_ok=True)
        with open(html_path, 'w', encoding='utf-8') as f:
            f.write(html)
        print(f"  HTML guardado en: {html_path}")

        # Tomar screenshot
        screenshot_path = Path(__file__).parent.parent / "data" / "debug" / f"bcn_{id_norma}.png"
        await page.screenshot(path=str(screenshot_path), full_page=True)
        print(f"  Screenshot guardado en: {screenshot_path}")

        await browser.close()

        print("\n" + "=" * 70)
        print("EXPLORACIÓN COMPLETADA")
        print("=" * 70)


if __name__ == "__main__":
    asyncio.run(explore_vinculaciones("250604"))
