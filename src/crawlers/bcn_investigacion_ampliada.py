#!/usr/bin/env python3
"""
BCN - Investigación AMPLIADA de materias de energía.
Búsqueda exhaustiva con términos específicos del sector eléctrico chileno.
"""

import asyncio
import json
from pathlib import Path
from collections import Counter, defaultdict
from urllib.parse import quote
from playwright.async_api import async_playwright
from playwright_stealth import Stealth

PROJECT_ROOT = Path(__file__).parent.parent.parent
DATA_RAW = PROJECT_ROOT / "data" / "raw"

# TÉRMINOS DE BÚSQUEDA AMPLIADOS
# Basados en la normativa eléctrica chilena y el Decreto 62
SEARCH_TERMS = [
    # Instituciones clave
    "Coordinador Eléctrico Nacional",
    "Coordinador Independiente Sistema Eléctrico",
    "Comisión Nacional de Energía",
    "CNE energía",
    "Ministerio de Energía",
    "Superintendencia de Electricidad",
    "SEC electricidad",

    # Leyes fundamentales
    "Ley General de Servicios Eléctricos",
    "DFL 1 energía",
    "DFL 4 energía",
    "Decreto 62 transferencias",
    "Decreto 327 electricidad",

    # Transmisión
    "transmisión eléctrica",
    "sistema de transmisión",
    "líneas de transmisión",
    "transmisión troncal",
    "transmisión zonal",
    "transmisión dedicada",
    "subestación eléctrica",
    "expansión transmisión",

    # Generación
    "generación eléctrica",
    "central generadora",
    "potencia instalada",
    "transferencias de potencia",
    "empresas generadoras",
    "centrales eléctricas",
    "potencia firme",
    "potencia suficiente",
    "balance de potencia",

    # Distribución
    "distribución eléctrica",
    "empresas distribuidoras",
    "concesionaria distribución",
    "redes de distribución",

    # Tarifas y precios
    "tarifas eléctricas",
    "precio nudo",
    "precios nudo",
    "fijación de precios",
    "valor agregado distribución",
    "peajes transmisión",
    "estabilización tarifaria",

    # Sistema eléctrico
    "sistema eléctrico nacional",
    "sistema interconectado",
    "despacho económico",
    "programación operación",
    "costo marginal",
    "demanda eléctrica",

    # Servicios complementarios
    "servicios complementarios",
    "reserva en giro",
    "control de frecuencia",
    "control de tensión",

    # Energías renovables
    "energías renovables",
    "ERNC",
    "energía solar",
    "energía eólica",
    "fotovoltaica",
    "pequeños medios generación",
    "PMGD",
    "net billing",
    "generación distribuida",

    # Medio ambiente energía
    "huella de carbono electricidad",
    "descarbonización",
    "retiro centrales carbón",
    "impuesto verde",

    # Eficiencia energética
    "eficiencia energética",
    "etiquetado energético",
    "consumo energético",

    # Combustibles
    "combustibles eléctricos",
    "GNL energía",
    "gas natural electricidad",
    "hidrocarburos energía",

    # Almacenamiento
    "almacenamiento energía",
    "baterías eléctricas",
    "sistemas almacenamiento",

    # Electromovilidad
    "electromovilidad",
    "vehículos eléctricos",
    "carga eléctrica vehículos",

    # Clientes
    "clientes regulados electricidad",
    "clientes libres electricidad",
    "electrodependientes",
    "suministro eléctrico",

    # Mercado eléctrico
    "mercado eléctrico",
    "licitaciones suministro",
    "contratos suministro eléctrico",
    "comercializadores electricidad",

    # Normas técnicas
    "norma técnica electricidad",
    "norma técnica conexión",
    "reglamento eléctrico",
    "instalaciones eléctricas",

    # Seguridad
    "seguridad eléctrica",
    "calidad de servicio eléctrico",
    "interrupciones eléctricas",
    "fallas eléctricas",

    # Concesiones
    "concesión eléctrica",
    "servidumbre eléctrica",

    # Términos adicionales del Decreto 62
    "potencia de suficiencia",
    "factor de planta",
    "ingresos tarifarios",
    "margen de reserva",
    "demanda máxima",
    "energía anual",
]

# Materias para clasificar
MATERIAS_KEYWORDS = {
    "Transmisión Eléctrica": [
        "transmisión", "línea de transmisión", "sistema de transmisión",
        "troncal", "zonal", "subestación", "expansión"
    ],
    "Generación Eléctrica": [
        "generación", "generadora", "central generadora", "potencia instalada",
        "potencia firme", "factor de planta", "centrales"
    ],
    "Transferencias de Potencia": [
        "transferencia", "potencia de suficiencia", "balance de potencia",
        "margen de reserva", "demanda máxima"
    ],
    "Distribución Eléctrica": [
        "distribución", "distribuidora", "concesionaria", "red de distribución"
    ],
    "Tarifas y Precios": [
        "tarifa", "precio", "nudo", "fijación de precios", "valor agregado",
        "peaje", "estabilización tarifaria", "costo marginal"
    ],
    "Energías Renovables": [
        "renovable", "ERNC", "solar", "eólica", "fotovoltaic", "PMGD",
        "net billing", "generación distribuida"
    ],
    "Eficiencia Energética": [
        "eficiencia energética", "ahorro energético", "consumo energético",
        "etiquetado"
    ],
    "Servicios Complementarios": [
        "servicios complementarios", "SSCC", "frecuencia", "reserva en giro",
        "tensión"
    ],
    "Operación del Sistema": [
        "operación", "coordinación", "despacho", "programación", "coordinador"
    ],
    "Seguridad y Calidad": [
        "seguridad", "calidad de servicio", "continuidad", "interrupcion",
        "falla"
    ],
    "Medio Ambiente": [
        "ambiental", "emisiones", "impacto ambiental", "huella de carbono",
        "descarbonización", "carbón"
    ],
    "Combustibles": [
        "combustible", "petróleo", "gas natural", "GNL", "diésel",
        "hidrocarburo"
    ],
    "Almacenamiento": [
        "almacenamiento", "batería", "sistemas de almacenamiento"
    ],
    "Electromovilidad": [
        "electromovilidad", "vehículo eléctrico", "carga eléctrica"
    ],
    "Interconexión": [
        "interconexión", "sistema interconectado"
    ],
    "Concesiones": [
        "concesión", "servidumbre", "derecho de paso"
    ],
    "Clientes y Usuarios": [
        "cliente", "usuario", "consumidor", "electrodependiente",
        "regulado", "libre"
    ],
    "Mercado Eléctrico": [
        "mercado", "licitación", "contrato de suministro", "comercializa"
    ],
    "Infraestructura": [
        "subestación", "infraestructura", "instalacion"
    ],
    "Normas Técnicas": [
        "norma técnica", "reglamento técnico", "especificación técnica",
        "reglamento eléctrico"
    ],
    "Institucionalidad": [
        "superintendencia", "SEC", "fiscalización", "sanción", "CNE",
        "ministerio"
    ],
}


async def search_bcn(page, term: str, max_pages: int = 3) -> list:
    """Búsqueda en BCN con múltiples páginas."""
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

                    // Fecha DD-MMM-YYYY
                    const dateMatch = line.match(/^(\\d{2})-([A-Z]{3})-(\\d{4})$/i);
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
                        // Tipo de norma
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


def clasificar_materias(norma: dict) -> list:
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
    print("BCN - INVESTIGACIÓN AMPLIADA DE MATERIAS DE ENERGÍA")
    print("=" * 70)
    print(f"Total términos de búsqueda: {len(SEARCH_TERMS)}")

    all_normas = {}
    search_results = defaultdict(list)

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)
        context = await browser.new_context()

        stealth = Stealth()
        await stealth.apply_stealth_async(context)
        page = await context.new_page()

        for i, term in enumerate(SEARCH_TERMS, 1):
            print(f"\n[{i}/{len(SEARCH_TERMS)}] Buscando: '{term}'...")
            normas = await search_bcn(page, term, max_pages=2)

            nuevas = 0
            for n in normas:
                key = f"{n['fecha']}_{n.get('tipo', '')[:30]}"
                if key not in all_normas:
                    n['busqueda_original'] = term
                    n['materias'] = clasificar_materias(n)
                    all_normas[key] = n
                    nuevas += 1
                    search_results[term].append(n)

            print(f"    Encontradas: {len(normas)}, Nuevas: {nuevas}")
            await asyncio.sleep(1)

        await browser.close()

    # Procesar resultados
    print("\n" + "=" * 70)
    print("PROCESANDO RESULTADOS")
    print("=" * 70)

    normas_list = list(all_normas.values())

    # Clasificar por materia
    materias_count = Counter()
    materias_normas = defaultdict(list)
    for n in normas_list:
        for m in n['materias']:
            materias_count[m] += 1
            materias_normas[m].append(n)

    # Por año
    años_count = Counter()
    for n in normas_list:
        años_count[n.get('año', 0)] += 1

    # Por tipo
    tipos_count = Counter()
    for n in normas_list:
        tipo = n.get('tipo', '').split()[0] if n.get('tipo') else 'OTRO'
        tipos_count[tipo] += 1

    # Guardar
    DATA_RAW.mkdir(parents=True, exist_ok=True)
    output = DATA_RAW / "bcn_investigacion_ampliada.json"

    save_data = {
        "resumen": {
            "total_normas": len(normas_list),
            "terminos_busqueda": len(SEARCH_TERMS),
            "por_materia": dict(materias_count.most_common()),
            "por_año": dict(sorted(años_count.items(), reverse=True)),
            "por_tipo": dict(tipos_count.most_common()),
        },
        "materias": {k: v for k, v in materias_normas.items()},
        "todas_las_normas": normas_list,
    }

    with open(output, 'w', encoding='utf-8') as f:
        json.dump(save_data, f, indent=2, ensure_ascii=False)

    # Mostrar resultados
    print("\n" + "=" * 70)
    print("RESUMEN FINAL")
    print("=" * 70)

    print(f"\nTotal normas únicas encontradas: {len(normas_list)}")
    print(f"Términos de búsqueda utilizados: {len(SEARCH_TERMS)}")

    print("\n" + "-" * 40)
    print("POR MATERIA:")
    print("-" * 40)
    for materia, count in materias_count.most_common(25):
        print(f"  {materia}: {count}")

    print("\n" + "-" * 40)
    print("POR TIPO DE NORMA:")
    print("-" * 40)
    for tipo, count in tipos_count.most_common():
        print(f"  {tipo}: {count}")

    print("\n" + "-" * 40)
    print("POR AÑO (últimos 15):")
    print("-" * 40)
    for año, count in sorted(años_count.items(), reverse=True)[:15]:
        print(f"  {año}: {count}")

    print(f"\n\nGuardado: {output}")

    # Mostrar taxonomía de materias con ejemplos
    print("\n" + "=" * 70)
    print("TAXONOMÍA DE MATERIAS ELÉCTRICAS")
    print("=" * 70)

    for materia, count in materias_count.most_common():
        if count > 0:
            print(f"\n{materia} ({count} normas)")
            ejemplos = materias_normas[materia][:3]
            for ej in ejemplos:
                print(f"  - [{ej['fecha']}] {ej.get('tipo', '')[:50]}")

    return save_data


if __name__ == "__main__":
    asyncio.run(main())
