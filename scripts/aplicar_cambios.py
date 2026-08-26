"""Aplicar al corpus los cambios que el monitor detectó. Cierra el ciclo de B4.

Hasta ahora el monitor sabía decir *"la norma X cambió"* y ahí se quedaba: el corpus seguía
respondiendo con el texto viejo. `scripts/actualizar_norma.py` da el camino técnico; esto es
lo que lo conecta con los eventos.

**No aplica solo por existir el evento.** Un `texto_modificado` puede ser un cambio real o un
scrape a medias que se le parece, así que cada norma pasa por las mismas guardas de
`actualizar_norma`: identidad, el texto no puede encoger más de 10 %, y el articulado tampoco.
Lo que no pasa queda listado para mirar a mano, no se fuerza.

Flujo completo:
    monitor_run.sh  ->  norma_evento (texto_modificado)
    aplicar_cambios ->  bajar_por_id + actualizar_norma  (con guardas)
    reproceso       ->  duplicados · derogaciones · proceso · obligaciones · citas

  PYTHONPATH=. venv/bin/python -m scripts.aplicar_cambios [--aplicar]
"""
import argparse
import asyncio
import subprocess
import sys
from pathlib import Path

from psycopg.rows import dict_row

from src.components.vectorstore import with_connection

DIR = Path("data/normas_completas/nuevas")


def pendientes():
    """Normas con evento de cambio de texto que todavia no se aplico al corpus."""
    with with_connection() as c, c.cursor(row_factory=dict_row) as cur:
        cur.execute("""
            SELECT e.id, e.id_norma, e.detectado_en, e.impacto,
                   n.tipo, n.numero, n.titulo
            FROM norma_evento e JOIN normas n ON n.id_norma = e.id_norma
            WHERE e.tipo_evento = 'texto_modificado'
              AND coalesce((e.impacto->>'aplicado')::boolean, false) = false
            ORDER BY e.detectado_en
        """)
        return cur.fetchall()


def main(aplicar=False):
    ev = pendientes()
    print(f"eventos de cambio SIN aplicar: {len(ev)}")
    if not ev:
        print("  nada que hacer — el monitor no detecto cambios de texto pendientes")
        return
    for e in ev:
        print(f"  {e['tipo']} {e['numero']:<8} ({e['id_norma']})  detectado {e['detectado_en']:%Y-%m-%d}")

    if not aplicar:
        print("\n(simulacion — usar --aplicar para bajar y reemplazar)")
        return

    for e in ev:
        nid = e["id_norma"]
        print(f"\n=== {e['tipo']} {e['numero']} ({nid}) ===", flush=True)
        # 1. bajar de nuevo, con las guardas de identidad y dominio de bajar_por_id
        r = subprocess.run([sys.executable, "-m", "scripts.bajar_por_id",
                            f"{nid}:{e['tipo']}:{e['numero']}"],
                           capture_output=True, text=True, timeout=900)
        print(r.stdout[-600:] if r.stdout else "(sin salida)", flush=True)
        if not (DIR / f"{nid}.json").exists():
            print("  no se pudo bajar — se deja el evento SIN aplicar", flush=True)
            continue
        # 2. reemplazar, con las guardas de largo y de articulado
        r = subprocess.run([sys.executable, "-m", "scripts.actualizar_norma", nid, "--aplicar"],
                           capture_output=True, text=True, timeout=3600)
        salida = r.stdout or ""
        print(salida[-900:], flush=True)
        if "ACTUALIZADA" not in salida:
            # las guardas lo frenaron: queda para revisar a mano, NO se marca aplicado
            print("  guardas frenaron el reemplazo — evento sigue pendiente", flush=True)
            continue
        with with_connection() as c, c.cursor() as cur:
            cur.execute("""UPDATE norma_evento
                           SET impacto = coalesce(impacto,'{}'::jsonb)
                               || jsonb_build_object('aplicado', true)
                           WHERE id = %s""", (e["id"],))
            c.commit()
        print("  evento marcado como aplicado", flush=True)

    print("\n⚠️ despues de esto hay que correr el reproceso:")
    print("   duplicados · derogaciones · proceso · obligaciones · citas")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--aplicar", action="store_true")
    main(ap.parse_args().aplicar)
