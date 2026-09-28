#!/usr/bin/env python3
"""
Actualizar el JSON estructurado del D.62 con las vinculaciones extraídas.
"""

import json
from pathlib import Path

def main():
    base = Path(__file__).parent.parent / "data"

    # Cargar vinculaciones extraídas
    vinc_path = base / "vinculaciones" / "250604.json"
    with open(vinc_path, 'r', encoding='utf-8') as f:
        vinculaciones = json.load(f)

    print("Vinculaciones extraídas:")
    for mod in vinculaciones['modificada_por']:
        print(f"  - {mod['tipo']} {mod['numero']} (id: {mod['id_norma']})")

    # Cargar JSON estructurado actual
    d62_path = base / "normas_estructuradas" / "decretos" / "decreto_62.json"
    with open(d62_path, 'r', encoding='utf-8') as f:
        d62 = json.load(f)

    print(f"\nModificaciones actuales en D.62:")
    for mod in d62.get('relaciones', {}).get('modificada_por', []):
        print(f"  - {mod['tipo']} {mod['numero']} (id: {mod.get('id_norma', 'N/A')})")

    # Actualizar con las nuevas vinculaciones
    nuevas_mods = []
    for mod in vinculaciones['modificada_por']:
        nuevas_mods.append({
            'tipo': mod['tipo'],
            'numero': mod['numero'],
            'id_norma': mod['id_norma'],
            'organismo': None,
            'articulo_modificador': None,
            'fecha_do': None,
            'fuente': mod['fuente']
        })

    # Reemplazar la lista de modificaciones
    d62['relaciones']['modificada_por'] = nuevas_mods

    # Agregar timestamp de actualización
    d62['vinculaciones_actualizadas'] = vinculaciones['extracted_at']

    # Guardar
    with open(d62_path, 'w', encoding='utf-8') as f:
        json.dump(d62, f, indent=2, ensure_ascii=False)

    print(f"\n✅ Actualizado: {d62_path}")
    print(f"\nNuevas modificaciones:")
    for mod in nuevas_mods:
        print(f"  - {mod['tipo']} {mod['numero']} (id: {mod['id_norma']})")

    # También actualizar el índice de relaciones bidireccionales
    relaciones_path = base / "normas_estructuradas" / "relaciones_bidireccionales.json"

    nuevas_relaciones = []
    for mod in nuevas_mods:
        nuevas_relaciones.append({
            "origen_id": mod['id_norma'],
            "origen": f"{mod['tipo']} {mod['numero']}",
            "destino_id": "250604",
            "destino": "DECRETO 62",
            "tipo_relacion": "MODIFICA",
            "fecha_do": mod.get('fecha_do'),
            "articulo_modificador": mod.get('articulo_modificador'),
            "organismo": mod.get('organismo')
        })

    with open(relaciones_path, 'w', encoding='utf-8') as f:
        json.dump({
            "generado": vinculaciones['extracted_at'],
            "total": len(nuevas_relaciones),
            "relaciones": nuevas_relaciones
        }, f, indent=2, ensure_ascii=False)

    print(f"\n✅ Actualizado: {relaciones_path}")


if __name__ == "__main__":
    main()
