#!/usr/bin/env python3
"""
BCN - Exploración completa de la estructura del sitio.
Objetivo: Descubrir todas las formas de buscar y navegar.
"""

import asyncio
import json
from pathlib import Path
from playwright.async_api import async_playwright
from playwright_stealth import Stealth

PROJECT_ROOT = Path(__file__).parent.parent.parent
DATA_RAW = PROJECT_ROOT / "data" / "raw"


async def explore_homepage(page):
    """Explora la página principal de BCN."""
    print("\n" + "=" * 60)
    print("1. PÁGINA PRINCIPAL - Opciones de navegación")
    print("=" * 60)

    await page.goto("https://www.bcn.cl/leychile/", wait_until='networkidle', timeout=30000)
    await asyncio.sleep(3)

    # Extraer menús y enlaces de navegación
    nav_data = await page.evaluate('''() => {
        const data = {
            menus: [],
            links: [],
            forms: [],
            selects: [],
            buttons: []
        };

        // Menús de navegación
        document.querySelectorAll('nav, .menu, .nav, [role="navigation"]').forEach(nav => {
            const items = [];
            nav.querySelectorAll('a').forEach(a => {
                if (a.textContent.trim()) {
                    items.push({
                        text: a.textContent.trim().substring(0, 50),
                        href: a.href
                    });
                }
            });
            if (items.length > 0) {
                data.menus.push(items);
            }
        });

        // Todos los enlaces principales
        document.querySelectorAll('a').forEach(a => {
            const text = a.textContent.trim();
            const href = a.href || '';
            if (text && href && !href.includes('javascript') && text.length > 2) {
                data.links.push({
                    text: text.substring(0, 80),
                    href: href
                });
            }
        });

        // Formularios de búsqueda
        document.querySelectorAll('form, [role="search"]').forEach(form => {
            const inputs = [];
            form.querySelectorAll('input, select').forEach(el => {
                inputs.push({
                    type: el.type || el.tagName,
                    name: el.name || el.id,
                    placeholder: el.placeholder || ''
                });
            });
            data.forms.push({
                action: form.action,
                inputs: inputs
            });
        });

        // Selectores (dropdowns)
        document.querySelectorAll('select').forEach(sel => {
            const options = [];
            sel.querySelectorAll('option').forEach(opt => {
                if (opt.value) {
                    options.push({value: opt.value, text: opt.textContent.trim()});
                }
            });
            data.selects.push({
                name: sel.name || sel.id,
                options: options.slice(0, 20)  // Limitar
            });
        });

        return data;
    }''')

    print(f"\n  Menús encontrados: {len(nav_data['menus'])}")
    print(f"  Enlaces totales: {len(nav_data['links'])}")
    print(f"  Formularios: {len(nav_data['forms'])}")
    print(f"  Selectores: {len(nav_data['selects'])}")

    # Mostrar enlaces únicos relevantes
    unique_links = {}
    for link in nav_data['links']:
        href = link['href']
        if 'leychile' in href and href not in unique_links:
            unique_links[href] = link['text']

    print("\n  Enlaces principales de LeyChile:")
    for href, text in list(unique_links.items())[:20]:
        print(f"    - {text[:40]}: {href}")

    return nav_data


async def explore_search_page(page):
    """Explora la página de búsqueda avanzada."""
    print("\n" + "=" * 60)
    print("2. PÁGINA DE BÚSQUEDA - Filtros disponibles")
    print("=" * 60)

    # Probar diferentes URLs de búsqueda
    search_urls = [
        "https://www.bcn.cl/leychile/busqueda",
        "https://www.bcn.cl/leychile/consulta/busqueda_avanzada_702",
        "https://www.bcn.cl/leychile/Consulta/busqueda_702",
    ]

    for url in search_urls:
        print(f"\n  Probando: {url}")
        try:
            await page.goto(url, wait_until='networkidle', timeout=15000)
            await asyncio.sleep(2)

            title = await page.title()
            print(f"    Título: {title}")

            # Ver si hay formulario de búsqueda
            forms = await page.query_selector_all('form')
            print(f"    Formularios: {len(forms)}")

            selects = await page.query_selector_all('select')
            print(f"    Selectores: {len(selects)}")

            # Extraer opciones de selectores
            if selects:
                for i, sel in enumerate(selects[:3]):
                    name = await sel.get_attribute('name') or await sel.get_attribute('id') or f'select_{i}'
                    options = await sel.query_selector_all('option')
                    print(f"      Selector '{name}': {len(options)} opciones")

        except Exception as e:
            print(f"    Error: {e}")


async def explore_indices(page):
    """Explora los índices temáticos."""
    print("\n" + "=" * 60)
    print("3. ÍNDICES Y CATEGORÍAS")
    print("=" * 60)

    # URLs comunes de índices en sitios de legislación
    index_urls = [
        ("Materias", "https://www.bcn.cl/leychile/consulta/listado_n_702"),
        ("Organismos", "https://www.bcn.cl/leychile/consulta/listado_org"),
        ("Tipos", "https://www.bcn.cl/leychile/consulta/listado_tipo"),
        ("Índice A-Z", "https://www.bcn.cl/leychile/consulta/indice_702"),
    ]

    for name, url in index_urls:
        print(f"\n  {name}: {url}")
        try:
            await page.goto(url, wait_until='networkidle', timeout=15000)
            await asyncio.sleep(2)

            # Verificar si existe
            content = await page.content()
            if "no encontrado" in content.lower() or "404" in content:
                print("    -> No existe (404)")
                continue

            # Contar enlaces
            links = await page.query_selector_all('a')
            print(f"    -> {len(links)} enlaces")

            # Extraer primeras categorías
            categories = await page.evaluate('''() => {
                const cats = [];
                document.querySelectorAll('a').forEach(a => {
                    const href = a.href || '';
                    const text = a.textContent.trim();
                    if ((href.includes('listado') || href.includes('agr=') || href.includes('sub='))
                        && text.length > 2 && text.length < 100) {
                        cats.push({text: text, href: href});
                    }
                });
                return cats.slice(0, 10);
            }''')

            for cat in categories[:5]:
                print(f"      - {cat['text'][:50]}")

        except Exception as e:
            print(f"    Error: {e}")


async def explore_after_search(page):
    """Explora los filtros que aparecen después de una búsqueda."""
    print("\n" + "=" * 60)
    print("4. FILTROS POST-BÚSQUEDA (Refinar búsqueda)")
    print("=" * 60)

    # Hacer una búsqueda y ver qué filtros aparecen
    await page.goto(
        "https://www.bcn.cl/leychile/Consulta/listaresultadosimple?cadena=energia",
        wait_until='networkidle',
        timeout=30000
    )
    await asyncio.sleep(3)

    # Buscar panel de filtros
    filters = await page.evaluate('''() => {
        const data = {
            refine_options: [],
            sidebar_links: [],
            filter_selects: []
        };

        // Buscar sección "Refinar" o filtros laterales
        const text = document.body.innerText;
        const lines = text.split('\\n');

        let inRefineSection = false;
        for (const line of lines) {
            const t = line.trim();
            if (t.includes('Refinar') || t.includes('Filtrar')) {
                inRefineSection = true;
            }
            if (inRefineSection && t.length > 2 && t.length < 50) {
                data.refine_options.push(t);
            }
            if (data.refine_options.length > 20) break;
        }

        // Buscar enlaces de filtro en sidebar
        document.querySelectorAll('.sidebar a, .filtro a, .refinar a, aside a').forEach(a => {
            const text = a.textContent.trim();
            const href = a.href || '';
            if (text && href) {
                data.sidebar_links.push({text: text.substring(0, 50), href: href});
            }
        });

        // Selectores de filtro
        document.querySelectorAll('select').forEach(sel => {
            const name = sel.name || sel.id;
            const optCount = sel.querySelectorAll('option').length;
            data.filter_selects.push({name: name, options: optCount});
        });

        return data;
    }''')

    print("\n  Opciones de refinamiento encontradas:")
    for opt in filters['refine_options'][:15]:
        print(f"    - {opt}")

    print(f"\n  Selectores de filtro: {len(filters['filter_selects'])}")
    for sel in filters['filter_selects']:
        print(f"    - {sel['name']}: {sel['options']} opciones")

    # También extraer texto visible para análisis
    body_text = await page.inner_text('body')

    return filters, body_text[:3000]


async def main():
    print("=" * 60)
    print("BCN - ANÁLISIS COMPLETO DE ESTRUCTURA")
    print("=" * 60)

    results = {}

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)
        context = await browser.new_context()

        stealth = Stealth()
        await stealth.apply_stealth_async(context)
        page = await context.new_page()

        # 1. Explorar homepage
        results['homepage'] = await explore_homepage(page)

        # 2. Explorar búsqueda
        await explore_search_page(page)

        # 3. Explorar índices
        await explore_indices(page)

        # 4. Explorar filtros post-búsqueda
        filters, sample_text = await explore_after_search(page)
        results['filters'] = filters
        results['sample_search_text'] = sample_text

        await browser.close()

    # Guardar resultados
    DATA_RAW.mkdir(parents=True, exist_ok=True)
    output = DATA_RAW / "bcn_estructura.json"
    with open(output, 'w', encoding='utf-8') as f:
        json.dump(results, f, indent=2, ensure_ascii=False)

    print(f"\n\nAnálisis guardado en: {output}")

    # Mostrar texto de muestra para análisis manual
    print("\n" + "=" * 60)
    print("TEXTO DE MUESTRA (página de búsqueda):")
    print("=" * 60)
    print(results.get('sample_search_text', '')[:2000])


if __name__ == "__main__":
    asyncio.run(main())
