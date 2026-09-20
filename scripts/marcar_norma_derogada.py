"""Marca TODOS los articulos de una norma como derogados, con la evidencia textual. Reversible.

Caso (2026-09-20): el D.S. 3.386 de 1935 (id 202975, 236 articulos) esta derogado desde 1998 por
el art. 329 letra b) del D.S. 327 (id 124102): "Deróganse ... b) El decreto supremo Nº 3.386, de
1935". BCN lo trae con estado DESCONOCIDO y el retrieval lo servia: el sistema lo cito en 5 de 16
preguntas reales (pub_gold) y en >= 8 de las 28 fallas de dev. El retrieval ya excluye
`articulos.derogado` (vectorstore.py, flag filtrar_derogados), asi que basta la marca.

Uso:  PYTHONPATH=. venv/bin/python -m scripts.marcar_norma_derogada 202975 124102/329 [--apply|--revertir]
"""
import json, sys
from src.storage.connection import with_connection

nid, evidencia = sys.argv[1], sys.argv[2]
modo = sys.argv[3] if len(sys.argv) > 3 else ""
with with_connection() as conn:
    cur = conn.cursor()
    if modo == "--revertir":
        cur.execute("UPDATE articulos SET derogado=false, metadata = metadata - 'derogado_por', updated_at=now() "
                    "WHERE id_norma=%s AND metadata->>'derogado_por'=%s", (nid, evidencia))
    else:
        cur.execute("SELECT count(*) FROM articulos WHERE id_norma=%s AND NOT coalesce(derogado,false)", (nid,))
        print("articulos vivos:", cur.fetchone()[0])
        if modo != "--apply":
            print("(simulacion; --apply para escribir)"); sys.exit()
        # solo los vivos: los ya derogados conservan su estado al revertir
        cur.execute("UPDATE articulos SET derogado=true, updated_at=now(), "
                    "metadata = coalesce(metadata,'{}'::jsonb) || %s::jsonb "
                    "WHERE id_norma=%s AND NOT coalesce(derogado,false)",
                    (json.dumps({"derogado_por": evidencia}), nid))
    print(modo, "filas:", cur.rowcount); conn.commit()
