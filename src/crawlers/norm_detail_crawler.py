#!/usr/bin/env python3
"""
Crawler para extraer contenido completo de una norma desde BCN.
Extrae: metadatos, texto completo, vinculaciones.
"""

import asyncio
import json
import hashlib
import re
from pathlib import Path
from datetime import datetime
from typing import Optional, Dict, Any
from dataclasses import dataclass, asdict

from playwright.async_api import async_playwright, Page
from playwright_stealth import Stealth


@dataclass
class NormData:
    """Datos extraídos de una norma."""
    id_norma: str
    tipo: str
    numero: str
    titulo: str
    fecha_publicacion: str
    fecha_promulgacion: Optional[str]
    organismo: str
    estado: str
    url: str
    texto_completo: str
    content_hash: str
    vinculaciones: Dict[str, list]
    versiones: list
    extracted_at: str


class NormDetailCrawler:
    """Crawler para extraer detalles completos de normas BCN."""

    BASE_URL = "https://www.bcn.cl/leychile/navegar"

    def __init__(self, headless: bool = True):
        self.headless = headless
        self.browser = None
        self.context = None

    async def __aenter__(self):
        await self.start()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.close()

    async def start(self):
        """Iniciar browser."""
        self.playwright = await async_playwright().start()
        self.browser = await self.playwright.chromium.launch(headless=self.headless)
        self.context = await self.browser.new_context()
        stealth = Stealth()
        await stealth.apply_stealth_async(self.context)

    async def close(self):
        """Cerrar browser."""
        if self.browser:
            await self.browser.close()
        if self.playwright:
            await self.playwright.stop()

    async def fetch_norm(self, id_norma: str) -> Optional[NormData]:
        """
        Extraer datos completos de una norma.

        Args:
            id_norma: ID de BCN (ej: "250604")

        Returns:
            NormData con todos los datos extraídos
        """
        url = f"{self.BASE_URL}?idNorma={id_norma}"
        page = await self.context.new_page()

        try:
            print(f"  Accediendo a: {url}")
            await page.goto(url, wait_until='networkidle', timeout=60000)
            await asyncio.sleep(3)

            # Extraer metadatos básicos
            metadata = await self._extract_metadata(page)

            # Extraer texto completo
            texto = await self._extract_texto_completo(page)

            # Extraer vinculaciones
            vinculaciones = await self._extract_vinculaciones(page)

            # Extraer versiones
            versiones = await self._extract_versiones(page)

            # Calcular hash del contenido
            content_hash = hashlib.sha256(texto.encode()).hexdigest()[:16]

            return NormData(
                id_norma=id_norma,
                tipo=metadata.get('tipo', ''),
                numero=metadata.get('numero', ''),
                titulo=metadata.get('titulo', ''),
                fecha_publicacion=metadata.get('fecha_publicacion', ''),
                fecha_promulgacion=metadata.get('fecha_promulgacion'),
                organismo=metadata.get('organismo', ''),
                estado=metadata.get('estado', 'DESCONOCIDO'),
                url=url,
                texto_completo=texto,
                content_hash=content_hash,
                vinculaciones=vinculaciones,
                versiones=versiones,
                extracted_at=datetime.now().isoformat()
            )

        except Exception as e:
            print(f"  ERROR: {e}")
            return None
        finally:
            await page.close()

    async def _extract_metadata(self, page: Page) -> dict:
        """Extraer metadatos de la norma."""
        return await page.evaluate('''() => {
            const data = {};

            // Título - buscar en encabezado
            const titulo = document.querySelector('h1, .titulo-norma, [class*="titulo"]');
            if (titulo) data.titulo = titulo.innerText.trim();

            // Buscar en el texto visible
            const bodyText = document.body.innerText;

            // Tipo y número (ej: "DECRETO 62")
            const tipoMatch = bodyText.match(/^(LEY|DECRETO|DFL|DL|RESOLUCIÓN|AUTO)\\s*(\\d+)/im);
            if (tipoMatch) {
                data.tipo = tipoMatch[1];
                data.numero = tipoMatch[2];
            }

            // Fecha publicación
            const fechaPubMatch = bodyText.match(/Fecha\\s*(?:de\\s*)?Publicación[:\\s]*(\\d{2}[-/]\\w{3}[-/]\\d{4})/i);
            if (fechaPubMatch) data.fecha_publicacion = fechaPubMatch[1];

            // Fecha promulgación
            const fechaPromMatch = bodyText.match(/Fecha\\s*(?:de\\s*)?Promulgación[:\\s]*(\\d{2}[-/]\\w{3}[-/]\\d{4})/i);
            if (fechaPromMatch) data.fecha_promulgacion = fechaPromMatch[1];

            // Organismo
            const orgMatch = bodyText.match(/Organismo[:\\s]*([^\\n]+)/i);
            if (orgMatch) data.organismo = orgMatch[1].trim();

            // Estado
            if (bodyText.includes('DEROGAD')) data.estado = 'DEROGADA';
            else if (bodyText.includes('VIGENTE')) data.estado = 'VIGENTE';
            else data.estado = 'DESCONOCIDO';

            return data;
        }''')

    async def _extract_texto_completo(self, page: Page) -> str:
        """Extraer texto completo de la norma."""
        texto = await page.evaluate('''() => {
            // Buscar contenedor principal del texto de la norma
            const containers = [
                document.querySelector('.cuerpo-norma'),
                document.querySelector('#texto-norma'),
                document.querySelector('[class*="contenido"]'),
                document.querySelector('article'),
                document.body
            ];

            for (const container of containers) {
                if (container && container.innerText.length > 500) {
                    return container.innerText;
                }
            }

            return document.body.innerText || '';
        }''')
        return texto.strip()

    async def _extract_vinculaciones(self, page: Page) -> dict:
        """
        Extraer vinculaciones (relaciones con otras normas).

        BCN muestra las modificaciones como links inline con la estructura:
        - Texto: "Decreto 70, ENERGÍA\nArt. primero N° 1\nD.O. 05.06.2024"
        - href: "...idNorma=1204012&idParte=10502404&idVersion=2024-06-05"

        Estos links contienen el idNorma del decreto modificador.
        """
        return await page.evaluate('''() => {
            const vinculaciones = {
                modifica_a: [],
                modificada_por: [],
                deroga_a: [],
                derogada_por: [],
                reglamenta: [],
                reglamentada_por: [],
                referencias: []  // Referencias a otras normas en el texto
            };

            // Extraer TODOS los links con idNorma (estos son las modificaciones inline)
            const links = document.querySelectorAll('a[href*="idNorma"]');
            const seenIds = new Set();

            for (const link of links) {
                const href = link.href || '';
                const text = link.innerText.trim();

                // Ignorar links vacíos o de navegación
                if (!text || text.length < 5) continue;

                // Extraer idNorma, idParte, idVersion del href
                const idNormaMatch = href.match(/idNorma=(\\d+)/);
                const idParteMatch = href.match(/idParte=(\\d+)/);
                const idVersionMatch = href.match(/idVersion=([\\d-]+)/);

                if (!idNormaMatch) continue;

                const idNorma = idNormaMatch[1];

                // Evitar duplicados
                const uniqueKey = `${idNorma}-${text.substring(0, 50)}`;
                if (seenIds.has(uniqueKey)) continue;
                seenIds.add(uniqueKey);

                // Parsear el texto del link para extraer info estructurada
                // Formato típico: "Decreto 70, ENERGÍA\\nArt. primero N° 1\\nD.O. 05.06.2024"
                const lines = text.split('\\n').map(l => l.trim()).filter(l => l);

                let tipo = null;
                let numero = null;
                let organismo = null;
                let articulo = null;
                let fecha_do = null;

                // Primera línea: "Decreto 70, ENERGÍA" o "Ley 20936"
                if (lines[0]) {
                    const tipoNumMatch = lines[0].match(/^(Decreto|Ley|DFL|DL|Resolución)\\s+(\\d+)(?:\\s+EXENTO)?[,\\s]*/i);
                    if (tipoNumMatch) {
                        tipo = tipoNumMatch[1].toUpperCase();
                        numero = tipoNumMatch[2];
                        // El resto es el organismo
                        const resto = lines[0].substring(tipoNumMatch[0].length).trim();
                        if (resto) organismo = resto;
                    }
                }

                // Buscar artículo y fecha en las otras líneas
                for (const line of lines.slice(1)) {
                    if (line.startsWith('Art.') || line.startsWith('art.')) {
                        articulo = line;
                    } else if (line.startsWith('D.O.') || line.startsWith('d.o.')) {
                        fecha_do = line.replace(/^D\\.O\\.\\s*/i, '').trim();
                    }
                }

                // Crear objeto de modificación
                const modificacion = {
                    id_norma: idNorma,
                    tipo: tipo,
                    numero: numero,
                    organismo: organismo,
                    articulo: articulo,
                    fecha_do: fecha_do,
                    texto_original: text,
                    id_parte: idParteMatch ? idParteMatch[1] : null,
                    id_version: idVersionMatch ? idVersionMatch[1] : null
                };

                // Estos links inline son modificaciones A esta norma (modificada_por)
                // porque aparecen junto a los artículos que fueron modificados
                if (tipo && numero) {
                    vinculaciones.modificada_por.push(modificacion);
                } else {
                    // Referencias generales sin parsear bien
                    vinculaciones.referencias.push({
                        id_norma: idNorma,
                        texto: text.substring(0, 200)
                    });
                }
            }

            // También buscar en el texto secciones explícitas de vinculaciones
            const bodyText = document.body.innerText;
            const sections = bodyText.split(/\\n/);

            let currentSection = null;
            for (const line of sections) {
                const lineLower = line.toLowerCase().trim();

                // Detectar sección
                if (lineLower.includes('modifica a:') || lineLower.includes('modifica el')) {
                    currentSection = 'modifica_a';
                } else if (lineLower.includes('deroga a:') || lineLower.includes('deroga el')) {
                    currentSection = 'deroga_a';
                } else if (lineLower.includes('reglamenta:') || lineLower.includes('reglamento de')) {
                    currentSection = 'reglamenta';
                }

                // Extraer referencias a normas (solo si no es un link que ya procesamos)
                if (currentSection && currentSection !== 'modificada_por') {
                    const normMatch = line.match(/(LEY|DECRETO|DFL|DL|RESOLUCIÓN)\\s+(?:N[°º]?\\s*)?(\\d+)/i);
                    if (normMatch) {
                        const exists = vinculaciones[currentSection].some(
                            v => v.tipo === normMatch[1].toUpperCase() && v.numero === normMatch[2]
                        );
                        if (!exists) {
                            vinculaciones[currentSection].push({
                                tipo: normMatch[1].toUpperCase(),
                                numero: normMatch[2],
                                descripcion: line.trim().substring(0, 200)
                            });
                        }
                    }
                }
            }

            return vinculaciones;
        }''')

    async def _extract_versiones(self, page: Page) -> list:
        """Extraer versiones históricas."""
        return await page.evaluate('''() => {
            const versiones = [];

            // Buscar selector de versiones
            const versionSelect = document.querySelector('select[name*="version"], #versiones, [class*="version"]');
            if (versionSelect) {
                const options = versionSelect.querySelectorAll('option');
                for (const opt of options) {
                    versiones.push({
                        id: opt.value,
                        descripcion: opt.innerText.trim()
                    });
                }
            }

            // También buscar en texto
            const bodyText = document.body.innerText;
            const versionMatches = bodyText.matchAll(/Versión\\s*(?:del)?\\s*(\\d{2}[-/]\\w{3}[-/]\\d{4})/gi);
            for (const match of versionMatches) {
                versiones.push({
                    fecha: match[1],
                    descripcion: match[0]
                });
            }

            return versiones;
        }''')

    def save_norm(self, norm: NormData, base_path: str = "data") -> dict:
        """
        Guardar norma en archivos.

        Args:
            norm: Datos de la norma
            base_path: Carpeta base para guardar

        Returns:
            dict con rutas de archivos creados
        """
        base = Path(base_path)

        # Determinar subcarpeta por tipo
        tipo_lower = norm.tipo.lower()
        if 'ley' in tipo_lower:
            subdir = 'leyes'
        elif 'dfl' in tipo_lower:
            subdir = 'dfl'
        elif 'decreto' in tipo_lower:
            subdir = 'decretos'
        elif 'resolución' in tipo_lower or 'resolucion' in tipo_lower:
            subdir = 'resoluciones'
        else:
            subdir = 'otros'

        # Crear nombre de archivo
        filename = f"{norm.tipo.lower()}_{norm.numero}".replace(' ', '_')
        if norm.fecha_publicacion:
            year_match = re.search(r'(\d{4})', norm.fecha_publicacion)
            if year_match:
                filename += f"_{year_match.group(1)}"

        # Guardar JSON completo
        json_path = base / "normas" / subdir / f"{filename}.json"
        json_path.parent.mkdir(parents=True, exist_ok=True)
        with open(json_path, 'w', encoding='utf-8') as f:
            json.dump(asdict(norm), f, indent=2, ensure_ascii=False)

        # Guardar texto plano
        txt_path = base / "textos" / f"{norm.id_norma}.txt"
        txt_path.parent.mkdir(parents=True, exist_ok=True)
        with open(txt_path, 'w', encoding='utf-8') as f:
            f.write(norm.texto_completo)

        return {
            'json': str(json_path),
            'txt': str(txt_path)
        }


async def fetch_single_norm(id_norma: str, save: bool = True) -> Optional[NormData]:
    """
    Función conveniente para descargar una sola norma.

    Args:
        id_norma: ID de BCN
        save: Si guardar los archivos

    Returns:
        NormData o None si falla
    """
    async with NormDetailCrawler(headless=True) as crawler:
        norm = await crawler.fetch_norm(id_norma)
        if norm and save:
            paths = crawler.save_norm(norm)
            print(f"  Guardado: {paths['json']}")
        return norm


# Test
if __name__ == "__main__":
    async def test():
        print("=" * 60)
        print("TEST: Descargar Decreto 62")
        print("=" * 60)

        norm = await fetch_single_norm("250604")

        if norm:
            print(f"\n✅ Norma descargada:")
            print(f"   Tipo: {norm.tipo}")
            print(f"   Número: {norm.numero}")
            print(f"   Título: {norm.titulo[:80]}...")
            print(f"   Estado: {norm.estado}")
            print(f"   Texto: {len(norm.texto_completo)} caracteres")
            print(f"   Hash: {norm.content_hash}")
            print(f"\n   Vinculaciones:")
            for tipo, lista in norm.vinculaciones.items():
                if lista:
                    print(f"     {tipo}: {len(lista)} referencias")
        else:
            print("❌ Error al descargar")

    asyncio.run(test())
