#!/usr/bin/env python3
"""
BCN - Investigación exhaustiva de materias de energía.
Basado en: Coordinador Eléctrico, CNE, Ministerio de Energía.
"""

import asyncio
import json
import re
from pathlib import Path
from collections import Counter, defaultdict
from urllib.parse import quote
from playwright.async_api import async_playwright
from playwright_stealth import Stealth

PROJECT_ROOT = Path(__file__).parent.parent.parent
DATA_RAW = PROJECT_ROOT / "data" / "raw"

# Instituciones a investigar
INSTITUCIONES = [
    {
        "nombre": "Coordinador Eléctrico Nacional",
        "busquedas": [
            "Coordinador Eléctrico Nacional",
            "Coordinador Independiente del Sistema Eléctrico",
        ]
    },
    {
        "nombre": "Comisión Nacional de Energía",
        "busquedas": [
            "Comisión Nacional de Energía",
            "CNE energía",
        ]
    },
    {
        "nombre": "Ministerio de Energía",
        "busquedas": [
            "Ministerio de Energía",
        ]
    },
]

# Palabras clave para clasificar materias
MATERIAS_KEYWORDS = {
    "Transmisión Eléctrica": ["transmisión", "línea de transmisión", "sistema de transmisión"],
    "Generación Eléctrica": ["generación", "generadora", "central generadora", "potencia instalada"],
    "Distribución Eléctrica": ["distribución", "distribuidora", "concesionaria"],
    "Tarifas y Precios": ["tarifa", "precio", "nudo", "fijación de precios", "valor agregado"],
    "Energías Renovables": ["renovable", "ERNC", "solar", "eólica", "fotovoltaic"],
    "Eficiencia Energética": ["eficiencia energética", "ahorro energético", "consumo energético"],
    "Servicios Complementarios": ["servicios complementarios", "SSCC", "frecuencia", "reserva"],
    "Operación del Sistema": ["operación", "coordinación", "despacho", "programación"],
    "Seguridad y Calidad": ["seguridad", "calidad de servicio", "continuidad", "interrupciones"],
    "Medio Ambiente": ["ambiental", "emisiones", "impacto ambiental", "huella de carbono"],
    "Combustibles": ["combustible", "petróleo", "gas natural", "GNL", "diésel"],
    "Almacenamiento": ["almacenamiento", "baterías", "sistemas de almacenamiento"],
    "Electromovilidad": ["electromovilidad", "vehículo eléctrico", "carga eléctrica"],
    "Interconexión": ["interconexión", "sistema interconectado"],
    "Concesiones": ["concesión", "servidumbre", "derecho de paso"],
    "Clientes y Usuarios": ["cliente", "usuario", "consumidor", "electrodependiente"],
    "Mercado Eléctrico": ["mercado", "licitación", "contrato de suministro", "comercialización"],
    "Infraestructura": ["subestación", "infraestructura", "instalaciones"],
    "Normas Técnicas": ["norma técnica", "reglamento técnico", "especificación técnica"],
    "Institucionalidad": ["superintendencia", "SEC", "fiscalización", "sanción"],
}


async def search_bcn_exhaustivo(page, term: str, max_pages: int = 3) -> list:
    """Búsqueda exhaustiva con múltiples páginas."""
    all_normas = []

    for page_num in range(max_pages):
        offset = page_num * 10
        url = f"https://www.bcn.cl/leychile/Consulta/listaresultadosimple?cadena={quote(term)}&offset={offset}"

        try:
            await page.goto(url, wait_until='networkidle', timeout=30000)
            await asyncio.sleep(2)

            normas = await page.evaluate('''() => {
                const results = [];
                if (!document.body) return results;

                const text = document.body.innerText || '';
                const lines = text.split('\\n');

                let current = null;

                for (let i = 0; i < lines.length; i++) {
                    const line = lines[i].trim();

                    // Fecha
                    const dateMatch = line.match(/^(\\d{2})-(\\w{3})-(\\d{4})$/i);
                    if (dateMatch) {
                        if (current && current.tipo) {
                            results.push(current);
                        }
                        current = {
                            fecha: line,
                            año: parseInt(dateMatch[3]),
                            tipo: '',
                            titulo: '',
                            organismo: ''
                        };
                        continue;
                    }

                    if (current) {
                        // Tipo
                        if (!current.tipo) {
                            const tipoMatch = line.match(/^(LEY|DECRETO|DFL|DL|RESOLUCIÓN|AUTO)/i);
                            if (tipoMatch) {
                                current.tipo = line.substring(0, 150);
                                continue;
                            }
                        }

                        // Título
                        if (current.tipo && !current.titulo && line.length > 15 &&
                            !line.match(/^MINISTERIO|^Alertas|^Vinculaciones|^SUBSECRETARIA/i)) {
                            current.titulo = line.substring(0, 300);
                        }

                        // Organismo
                        if (line.match(/^MINISTERIO|^COMISIÓN|^SUPERINTENDENCIA/i)) {
                            current.organismo = line.substring(0, 150);
                        }
                    }
                }

                if (current && current.tipo) {
                    results.push(current);
                }

                return results;
            }''')

            all_normas.extend(normas)

            # Si no hay resultados, parar
            if len(normas) == 0:
                break

        except Exception as e:
            print(f"      Error página {page_num + 1}: {e}")
            break

    return all_normas


def clasificar_materia(norma: dict) -> list:
    """Clasifica una norma en materias según su contenido."""
    texto = (norma.get('titulo', '') + ' ' + norma.get('tipo', '')).lower()
    materias = []

    for materia, keywords in MATERIAS_KEYWORDS.items():
        for kw in keywords:
            if kw.lower() in texto:
                materias.append(materia)
                break

    return materias if materias else ["Otros"]


async def main():
    print("=" * 70)
    print("BCN - INVESTIGACIÓN EXHAUSTIVA DE MATERIAS DE ENERGÍA")
    print("=" * 70)

    all_data = {
        "instituciones": {},
        "materias": defaultdict(list),
        "por_año": defaultdict(list),
        "por_tipo": defaultdict(list),
        "resumen": {}
    }

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)
        context = await browser.new_context()

        stealth = Stealth()
        await stealth.apply_stealth_async(context)
        page = await context.new_page()

        total_normas = {}

        for inst in INSTITUCIONES:
            print(f"\n{'='*70}")
            print(f"INSTITUCIÓN: {inst['nombre']}")
            print("=" * 70)

            inst_normas = []

            for busqueda in inst['busquedas']:
                print(f"\n  Buscando: '{busqueda}'...")
                normas = await search_bcn_exhaustivo(page, busqueda, max_pages=5)
                print(f"    Encontradas: {len(normas)}")

                for n in normas:
                    # Evitar duplicados
                    key = f"{n['fecha']}_{n.get('tipo', '')[:30]}"
                    if key not in total_normas:
                        n['institucion'] = inst['nombre']
                        n['materias'] = clasificar_materia(n)
                        total_normas[key] = n
                        inst_normas.append(n)

                await asyncio.sleep(1)

            all_data["instituciones"][inst['nombre']] = {
                "total": len(inst_normas),
                "normas": inst_normas
            }

            print(f"\n  Total únicas para {inst['nombre']}: {len(inst_normas)}")

        await browser.close()

    # Procesar y clasificar
    print("\n" + "=" * 70)
    print("PROCESANDO RESULTADOS")
    print("=" * 70)

    normas_list = list(total_normas.values())

    # Clasificar por materia
    materias_count = Counter()
    for n in normas_list:
        for m in n['materias']:
            materias_count[m] += 1
            all_data["materias"][m].append(n)

    # Por año
    años_count = Counter()
    for n in normas_list:
        año = n.get('año', 0)
        años_count[año] += 1
        all_data["por_año"][str(año)].append(n)

    # Por tipo
    tipos_count = Counter()
    for n in normas_list:
        tipo = n.get('tipo', '').split()[0] if n.get('tipo') else 'OTRO'
        tipos_count[tipo] += 1
        all_data["por_tipo"][tipo].append(n)

    # Resumen
    all_data["resumen"] = {
        "total_normas": len(normas_list),
        "por_institucion": {k: v["total"] for k, v in all_data["instituciones"].items()},
        "por_materia": dict(materias_count.most_common()),
        "por_año": dict(sorted(años_count.items(), reverse=True)),
        "por_tipo": dict(tipos_count.most_common()),
    }

    # Guardar
    DATA_RAW.mkdir(parents=True, exist_ok=True)
    output = DATA_RAW / "bcn_investigacion_energia.json"

    # Convertir defaultdict a dict para JSON
    save_data = {
        "resumen": all_data["resumen"],
        "materias": {k: v for k, v in all_data["materias"].items()},
        "por_año": {k: v for k, v in all_data["por_año"].items()},
        "instituciones": all_data["instituciones"],
    }

    with open(output, 'w', encoding='utf-8') as f:
        json.dump(save_data, f, indent=2, ensure_ascii=False)

    # Mostrar resultados
    print("\n" + "=" * 70)
    print("RESUMEN FINAL")
    print("=" * 70)

    print(f"\nTotal normas únicas: {len(normas_list)}")

    print("\n" + "-" * 40)
    print("POR INSTITUCIÓN:")
    print("-" * 40)
    for inst, count in all_data["resumen"]["por_institucion"].items():
        print(f"  {inst}: {count}")

    print("\n" + "-" * 40)
    print("POR MATERIA:")
    print("-" * 40)
    for materia, count in materias_count.most_common(20):
        print(f"  {materia}: {count}")

    print("\n" + "-" * 40)
    print("POR TIPO DE NORMA:")
    print("-" * 40)
    for tipo, count in tipos_count.most_common():
        print(f"  {tipo}: {count}")

    print("\n" + "-" * 40)
    print("POR AÑO (últimos 10):")
    print("-" * 40)
    for año, count in sorted(años_count.items(), reverse=True)[:10]:
        print(f"  {año}: {count}")

    print(f"\n\nGuardado: {output}")

    # Mostrar taxonomía de materias
    print("\n" + "=" * 70)
    print("TAXONOMÍA DE MATERIAS DE ENERGÍA (BCN)")
    print("=" * 70)

    for materia, count in materias_count.most_common():
        if count > 0:
            print(f"\n{materia} ({count} normas)")
            # Mostrar ejemplos
            ejemplos = all_data["materias"][materia][:3]
            for ej in ejemplos:
                print(f"  - [{ej['fecha']}] {ej.get('tipo', '')[:40]}")

    return all_data


if __name__ == "__main__":
    asyncio.run(main())
