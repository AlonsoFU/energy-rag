#!/usr/bin/env python3
"""
Compilar normas descargadas por los temas solicitados:
- Transferencias de energía
- Peajes de transmisión
- Servicios complementarios
- Distribución
- Medición
"""

import json
from pathlib import Path
from datetime import datetime
from collections import defaultdict


def main():
    # Cargar todas las normas
    input_path = Path("data/busquedas/normas_completas.json")
    with open(input_path, 'r', encoding='utf-8') as f:
        data = json.load(f)

    normas = data['normas']

    # Clasificar por temas de interés
    temas_solicitados = {
        "TRANSFERENCIAS_ENERGIA": {
            "descripcion": "Transferencias de energía y balance económico",
            "keywords": ["TRANSFERENCIAS", "ENERGIA"],
            "normas": []
        },
        "PEAJES_TRANSMISION": {
            "descripcion": "Peajes y remuneración de transmisión",
            "keywords": ["PEAJES", "TRANSMISION"],
            "normas": []
        },
        "SERVICIOS_COMPLEMENTARIOS": {
            "descripcion": "Servicios complementarios (SSCC) y control de frecuencia",
            "keywords": ["SSCC"],
            "normas": []
        },
        "DISTRIBUCION": {
            "descripcion": "Tarifas y regulación de distribución",
            "keywords": ["DISTRIBUCION"],
            "normas": []
        },
        "MEDICION": {
            "descripcion": "Medidores y sistemas de medición",
            "keywords": ["MEDICION"],
            "normas": []
        }
    }

    # Clasificar cada norma
    for norma in normas:
        temas_detectados = norma.get('temas_detectados', [])

        for tema_key, tema_info in temas_solicitados.items():
            # Ver si la norma tiene alguna keyword del tema
            for kw in tema_info['keywords']:
                if kw in temas_detectados:
                    resumen = {
                        'id_norma': norma['id_norma'],
                        'tipo': norma.get('tipo', '?'),
                        'numero': norma.get('numero', '?'),
                        'titulo': norma.get('titulo', '')[:100],
                        'temas': temas_detectados,
                        'url': norma.get('url', '')
                    }
                    if resumen not in tema_info['normas']:
                        tema_info['normas'].append(resumen)
                    break

    # Imprimir resumen
    print("=" * 80)
    print("NORMAS POR TEMA SOLICITADO")
    print("=" * 80)

    for tema_key, tema_info in temas_solicitados.items():
        print(f"\n{'─' * 80}")
        print(f"{tema_key}")
        print(f"  {tema_info['descripcion']}")
        print(f"  Total: {len(tema_info['normas'])} normas")
        print(f"{'─' * 80}")

        for n in tema_info['normas']:
            print(f"\n  [{n['tipo']} {n['numero']}] id={n['id_norma']}")
            print(f"    Temas: {', '.join(n['temas'])}")
            print(f"    URL: {n['url']}")

    # Guardar resultados
    output = {
        'fecha': datetime.now().isoformat(),
        'total_normas': len(normas),
        'temas': temas_solicitados
    }

    output_path = Path("data/busquedas/normas_por_tema_solicitado.json")
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(output, f, indent=2, ensure_ascii=False)

    print(f"\n{'=' * 80}")
    print("RESUMEN TOTAL")
    print(f"{'=' * 80}")
    print(f"\nTotal normas descargadas: {len(normas)}")
    print("\nPor tema solicitado:")
    for tema_key, tema_info in temas_solicitados.items():
        print(f"  {tema_key}: {len(tema_info['normas'])} normas")

    print(f"\nGuardado en: {output_path}")


if __name__ == "__main__":
    main()
