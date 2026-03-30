#!/usr/bin/env python3
"""
Generar resumen final de todas las normas descargadas.
"""

import json
from pathlib import Path
from datetime import datetime
from collections import defaultdict


def main():
    data = json.load(open("data/busquedas/normas_completas.json"))
    normas = {n['id_norma']: n for n in data['normas']}

    # Calcular pendientes
    ids_existentes = set(normas.keys())
    todas_vinc = set()
    for n in normas.values():
        for v in n.get('vinculaciones_ids', []):
            if len(v) > 3:
                todas_vinc.add(v)
    pendientes = todas_vinc - ids_existentes

    print("=" * 70)
    print("RESUMEN FINAL - NORMAS SECTOR ELÉCTRICO CHILE")
    print("=" * 70)

    print(f"\nFecha: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print(f"Total normas descargadas: {len(normas)}")
    print(f"Vinculaciones pendientes: {len(pendientes)}")
    print(f"Cobertura: {len(todas_vinc & ids_existentes)}/{len(todas_vinc)} ({len(todas_vinc & ids_existentes)/len(todas_vinc)*100:.1f}%)")

    # Por tipo
    print("\n" + "-" * 70)
    print("POR TIPO DE NORMA")
    print("-" * 70)
    por_tipo = defaultdict(list)
    for n in normas.values():
        por_tipo[n.get('tipo', 'OTRO')].append(n)

    for tipo in ['LEY', 'DECRETO', 'DFL', 'DL', 'RESOLUCION', 'DESCONOCIDO']:
        if tipo in por_tipo:
            print(f"\n{tipo} ({len(por_tipo[tipo])}):")
            for n in sorted(por_tipo[tipo], key=lambda x: x.get('numero', ''))[:10]:
                temas = ', '.join(n.get('temas_detectados', [])[:3])
                print(f"  {n.get('numero', '?'):8} | id={n['id_norma']:8} | {temas}")
            if len(por_tipo[tipo]) > 10:
                print(f"  ... y {len(por_tipo[tipo]) - 10} más")

    # Por tema
    print("\n" + "-" * 70)
    print("POR TEMA DETECTADO")
    print("-" * 70)
    por_tema = defaultdict(list)
    for n in normas.values():
        for t in n.get('temas_detectados', []):
            por_tema[t].append(f"{n.get('tipo', '?')} {n.get('numero', '?')}")

    for tema, lista in sorted(por_tema.items(), key=lambda x: -len(x[1])):
        print(f"  {tema:20} : {len(lista):3} normas")

    # Normas clave del sector eléctrico
    print("\n" + "-" * 70)
    print("NORMAS CLAVE IDENTIFICADAS")
    print("-" * 70)

    claves = [
        ('258171', 'DFL 4/20.018 - LGSE (Ley General de Servicios Eléctricos)'),
        ('1092695', 'Ley 20.936 - Sistema de Transmisión y Coordinador'),
        ('250604', 'Decreto 62 - Transferencias de Potencia'),
        ('1153949', 'Decreto 42 - Modifica Decreto 62'),
        ('1204012', 'Decreto 70 - Modifica Decreto 62'),
        ('1129970', 'Decreto 113 - Servicios Complementarios'),
        ('1122953', 'Decreto 4 - Reglamento Transmisión'),
        ('1146553', 'Decreto 10 - Valorización Transmisión'),
    ]

    for id_n, desc in claves:
        estado = "✓ Descargada" if id_n in normas else "✗ Pendiente"
        print(f"  [{estado}] {desc}")

    # Guardar resumen
    resumen = {
        'fecha': datetime.now().isoformat(),
        'estadisticas': {
            'total_normas': len(normas),
            'vinculaciones_pendientes': len(pendientes),
            'cobertura_porcentaje': round(len(todas_vinc & ids_existentes)/len(todas_vinc)*100, 1)
        },
        'por_tipo': {k: len(v) for k, v in por_tipo.items()},
        'por_tema': {k: len(v) for k, v in por_tema.items()},
        'pendientes': sorted(list(pendientes))
    }

    with open("data/busquedas/resumen_final.json", 'w', encoding='utf-8') as f:
        json.dump(resumen, f, indent=2, ensure_ascii=False)

    print(f"\n{'=' * 70}")
    print(f"Resumen guardado en: data/busquedas/resumen_final.json")
    print("=" * 70)


if __name__ == "__main__":
    main()
