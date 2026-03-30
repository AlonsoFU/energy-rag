#!/usr/bin/env python3
"""
Extrae vinculaciones completas de BCN incluyendo:
1. Modificaciones inline en el texto
2. Tabla de Versiones con historial completo
3. Links a páginas de MODIFICACION y CONCORDANCIA
"""

import asyncio
import json
import re
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Optional
from dataclasses import dataclass, asdict

from playwright.async_api import async_playwright, Page
from playwright_stealth import Stealth


@dataclass
class Modificacion:
    """Una modificación detectada."""
    id_norma: str
    tipo: str
    numero: str
    fecha_do: Optional[str] = None
    articulo: Optional[str] = None
    organismo: Optional[str] = None
    fuente: str = "inline"  # inline, versiones, vinculaciones_page


@dataclass
class VinculacionesCompletas:
    """Todas las vinculaciones de una norma."""
    id_norma: str
    modificada_por: List[Modificacion]
    versiones: List[dict]
    concordancias: List[dict]
    extracted_at: str


async def extract_vinculaciones(id_norma: str, headless: bool = True) -> VinculacionesCompletas:
    """
    Extraer todas las vinculaciones de una norma.

    Args:
        id_norma: ID BCN de la norma
        headless: Si ejecutar en modo headless

    Returns:
        VinculacionesCompletas con toda la información
    """
    print(f"\n{'=' * 60}")
    print(f"EXTRAYENDO VINCULACIONES DE NORMA {id_norma}")
    print(f"{'=' * 60}")

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=headless)
        context = await browser.new_context()
        stealth = Stealth()
        await stealth.apply_stealth_async(context)

        page = await context.new_page()

        url = f"https://www.bcn.cl/leychile/navegar?idNorma={id_norma}"
        print(f"\nAccediendo a: {url}")

        await page.goto(url, wait_until='networkidle', timeout=60000)
        await asyncio.sleep(3)

        # 1. Extraer modificaciones inline del texto
        print("\n1. Extrayendo modificaciones inline...")
        mods_inline = await _extract_inline_modifications(page)
        print(f"   Encontradas: {len(mods_inline)}")

        # 2. Extraer tabla de versiones
        print("\n2. Extrayendo tabla de versiones...")
        versiones = await _extract_versions_table(page)
        print(f"   Encontradas: {len(versiones)}")

        # 3. Extraer de página de MODIFICACION (link dedicado)
        print("\n3. Buscando página de vinculaciones MODIFICACION...")
        mods_page = await _extract_from_vinculaciones_page(page, id_norma, context)
        print(f"   Encontradas: {len(mods_page)}")

        await browser.close()

        # Consolidar modificaciones únicas
        all_mods = _consolidate_modifications(mods_inline, versiones, mods_page)

        print(f"\n{'=' * 60}")
        print(f"RESUMEN: {len(all_mods)} modificaciones únicas encontradas")
        print(f"{'=' * 60}")

        for mod in all_mods:
            print(f"  - {mod.tipo} {mod.numero} (id: {mod.id_norma}) [{mod.fuente}]")

        return VinculacionesCompletas(
            id_norma=id_norma,
            modificada_por=all_mods,
            versiones=versiones,
            concordancias=[],
            extracted_at=datetime.now().isoformat()
        )


async def _extract_inline_modifications(page: Page) -> List[Modificacion]:
    """Extraer modificaciones de los links inline en el texto."""
    mods = await page.evaluate('''() => {
        const modifications = [];

        // Los links de modificación tienen clase "n rs_skip_always"
        // y estructura: <a href="navegar?idNorma=XXX...">Decreto 70, ENERGÍA<br>Art. primero N° 1<br>D.O. 05.06.2024</a>
        const links = document.querySelectorAll('span.n a[href*="idNorma"]');

        for (const link of links) {
            const href = link.href || link.getAttribute('href') || '';
            const text = link.innerText || link.textContent || '';

            // Extraer idNorma del href
            const idMatch = href.match(/idNorma=(\\d+)/);
            if (!idMatch) continue;

            const idNorma = idMatch[1];

            // Parsear el texto: "Decreto 70, ENERGÍA\nArt. primero N° 1\nD.O. 05.06.2024"
            const lines = text.split(/\\n|<br>/i).map(l => l.trim()).filter(l => l);

            let tipo = null;
            let numero = null;
            let organismo = null;
            let articulo = null;
            let fecha_do = null;

            for (const line of lines) {
                // Tipo y número: "Decreto 70, ENERGÍA"
                const tipoMatch = line.match(/^(Decreto|Ley|DFL|DL|Resolucion)\\s+(\\d+)(?:\\s+EXENTO)?[,\\s]*(.*)?/i);
                if (tipoMatch) {
                    tipo = tipoMatch[1].toUpperCase();
                    numero = tipoMatch[2];
                    if (tipoMatch[3]) organismo = tipoMatch[3].trim();
                }

                // Artículo: "Art. primero N° 1"
                if (line.toLowerCase().startsWith('art')) {
                    articulo = line;
                }

                // Fecha D.O.: "D.O. 05.06.2024"
                const fechaMatch = line.match(/D\\.O\\.\\s*(\\d{2}\\.\\d{2}\\.\\d{4})/i);
                if (fechaMatch) {
                    fecha_do = fechaMatch[1];
                }
            }

            if (tipo && numero) {
                modifications.push({
                    id_norma: idNorma,
                    tipo: tipo,
                    numero: numero,
                    fecha_do: fecha_do,
                    articulo: articulo,
                    organismo: organismo,
                    fuente: 'inline'
                });
            }
        }

        return modifications;
    }''')

    return [Modificacion(**m) for m in mods]


async def _extract_versions_table(page: Page) -> List[dict]:
    """Extraer información de la tabla de versiones."""
    versiones = await page.evaluate('''() => {
        const versions = [];

        // Buscar la tabla de versiones
        // La tabla está en el tab "Versiones" y tiene columnas como Fecha, Modificaciones, etc.
        const tables = document.querySelectorAll('table');

        for (const table of tables) {
            const text = table.innerText.toLowerCase();
            if (!text.includes('modificacion') && !text.includes('versión')) continue;

            const rows = table.querySelectorAll('tr');
            for (const row of rows) {
                const cells = row.querySelectorAll('td, th');
                if (cells.length < 2) continue;

                // Buscar links a normas modificadoras en esta fila
                const links = row.querySelectorAll('a[href*="idNorma"]');

                for (const link of links) {
                    const href = link.href || link.getAttribute('href') || '';
                    const idMatch = href.match(/idNorma=(\\d+)/);
                    const versionMatch = href.match(/idVersion=([\\d-]+)/);

                    if (idMatch) {
                        versions.push({
                            id_norma: idMatch[1],
                            id_version: versionMatch ? versionMatch[1] : null,
                            text: link.innerText.trim(),
                            row_text: row.innerText.substring(0, 200)
                        });
                    }
                }
            }
        }

        return versions;
    }''')

    return versiones


async def _extract_from_vinculaciones_page(page: Page, id_norma: str, context) -> List[Modificacion]:
    """
    Ir a la página dedicada de vinculaciones/modificaciones.
    URL: /leychile/Consulta/nav_vinc_modificacion?idNorma=XXX
    """
    mods = []

    # Buscar el link a la página de modificaciones
    vinc_url = await page.evaluate('''() => {
        const link = document.querySelector('a[href*="nav_vinc_modificacion"]');
        return link ? link.href : null;
    }''')

    if not vinc_url:
        print("   No se encontró link a página de modificaciones")
        return mods

    print(f"   Accediendo a: {vinc_url}")

    vinc_page = await context.new_page()
    try:
        await vinc_page.goto(vinc_url, wait_until='networkidle', timeout=60000)
        await asyncio.sleep(2)

        # Extraer todas las modificaciones listadas
        mods_data = await vinc_page.evaluate('''() => {
            const modifications = [];

            // Buscar todas las filas/items con información de normas
            const items = document.querySelectorAll('tr, li, .item, [class*="norma"]');

            for (const item of items) {
                const text = item.innerText;
                const links = item.querySelectorAll('a[href*="idNorma"]');

                for (const link of links) {
                    const href = link.href || '';
                    const idMatch = href.match(/idNorma=(\\d+)/);
                    if (!idMatch) continue;

                    // Parsear tipo y número del texto
                    const normMatch = text.match(/(Decreto|Ley|DFL|DL|Resolucion)\\s+(?:N.?\\s*)?(\\d+)/i);

                    // Buscar fecha
                    const fechaMatch = text.match(/(\\d{2}[-\\/]\\w{3}[-\\/]\\d{4}|\\d{2}\\.\\d{2}\\.\\d{4})/);

                    if (normMatch) {
                        modifications.push({
                            id_norma: idMatch[1],
                            tipo: normMatch[1].toUpperCase(),
                            numero: normMatch[2],
                            fecha_do: fechaMatch ? fechaMatch[1] : null,
                            fuente: 'vinculaciones_page'
                        });
                    }
                }
            }

            return modifications;
        }''')

        mods = [Modificacion(**m) for m in mods_data]

    except Exception as e:
        print(f"   Error accediendo página de vinculaciones: {e}")
    finally:
        await vinc_page.close()

    return mods


def _consolidate_modifications(
    inline: List[Modificacion],
    versiones: List[dict],
    from_page: List[Modificacion]
) -> List[Modificacion]:
    """Consolidar modificaciones de todas las fuentes, eliminando duplicados."""
    seen = {}  # key: id_norma -> Modificacion

    # Prioridad: inline > versiones > from_page
    for mod in inline:
        key = mod.id_norma
        if key not in seen:
            seen[key] = mod

    # Agregar de versiones (parsear tipo/numero del texto si es posible)
    for v in versiones:
        key = v['id_norma']
        if key not in seen:
            # Intentar parsear tipo y número del texto
            text = v.get('text', '') + ' ' + v.get('row_text', '')
            match = re.search(r'(Decreto|Ley|DFL|DL|Resolución)\s+(?:N[°º]?\s*)?(\d+)', text, re.IGNORECASE)

            if match:
                seen[key] = Modificacion(
                    id_norma=key,
                    tipo=match.group(1).upper(),
                    numero=match.group(2),
                    fuente='versiones'
                )

    # Agregar de página de vinculaciones
    for mod in from_page:
        key = mod.id_norma
        if key not in seen:
            seen[key] = mod

    return list(seen.values())


def save_vinculaciones(vinc: VinculacionesCompletas, base_path: str = "data"):
    """Guardar vinculaciones a archivo JSON."""
    path = Path(base_path) / "vinculaciones" / f"{vinc.id_norma}.json"
    path.parent.mkdir(parents=True, exist_ok=True)

    data = {
        "id_norma": vinc.id_norma,
        "extracted_at": vinc.extracted_at,
        "modificada_por": [asdict(m) for m in vinc.modificada_por],
        "versiones": vinc.versiones,
        "concordancias": vinc.concordancias
    }

    with open(path, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

    print(f"\nGuardado en: {path}")
    return path


async def main():
    """Extraer vinculaciones del Decreto 62."""
    vinc = await extract_vinculaciones("250604")
    save_vinculaciones(vinc)


if __name__ == "__main__":
    asyncio.run(main())
