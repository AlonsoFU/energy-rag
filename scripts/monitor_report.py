"""B4.4 — notificacion: que cambio, y que respuestas del sistema quedaron en riesgo.

Lee los eventos pendientes de `norma_evento` y produce un informe legible. La parte que importa
no es "cambio la norma X" sino **"cambio la norma X, que citan estos N articulos tuyos"** —
`impacto.citada_por`, que viene del grafo de citas de B3.4.

  PYTHONPATH=. venv/bin/python -m scripts.monitor_report [--marcar] [--todos]

  --marcar   marca los eventos como notificados (no vuelven a salir)
  --todos    incluye los ya notificados
Salida: stdout + `docs/monitor-ultimo-informe.md`
"""
import sys
from pathlib import Path

from psycopg.rows import dict_row

from src.components.vectorstore import with_connection

TITULO = {
    "norma_nueva":        "NORMA NUEVA en el corpus",
    "texto_modificado":   "TEXTO MODIFICADO",
    "version_nueva":      "VERSION NUEVA publicada",
    "estado_cambiado":    "ESTADO CAMBIADO (posible derogacion)",
    "vinculacion_nueva":  "VINCULACION NUEVA (modifica/deroga)",
    "articulo_derogado":  "ARTICULO DEROGADO",
}
# los que pueden invalidar una respuesta ya entregada
CRITICOS = {"estado_cambiado", "texto_modificado", "articulo_derogado", "vinculacion_nueva"}


def main(marcar=False, todos=False):
    where = "" if todos else "WHERE NOT notificado"
    with with_connection() as c, c.cursor(row_factory=dict_row) as cur:
        cur.execute(f"""
            SELECT e.*, n.tipo, n.numero, n.titulo
            FROM norma_evento e LEFT JOIN normas n ON n.id_norma = e.id_norma
            {where} ORDER BY e.detectado_en DESC, e.id
        """)
        evs = cur.fetchall()

    L = ["# Informe del monitor normativo", ""]
    if not evs:
        L += ["Sin cambios pendientes."]
        print("sin cambios pendientes")
    else:
        crit = [e for e in evs if e["tipo_evento"] in CRITICOS and (e["impacto"] or {}).get("n_citas", 0) > 0]
        L += [f"- eventos pendientes: **{len(evs)}**",
              f"- de esos, **{len(crit)}** afectan a normas que el corpus CITA "
              f"(pueden invalidar respuestas ya entregadas)", ""]
        print(f"eventos: {len(evs)}  |  con impacto en el corpus: {len(crit)}")

        if crit:
            L += ["## ⚠️ Requieren revision", ""]
            for e in crit:
                nom = f"{e['tipo'] or ''} {e['numero'] or ''}".strip() or e["id_norma"]
                imp = e["impacto"] or {}
                L += [f"### {TITULO.get(e['tipo_evento'], e['tipo_evento'])} — {nom}",
                      f"`{e['id_norma']}` · detectado {e['detectado_en']:%Y-%m-%d %H:%M}",
                      f"- {str(e['titulo'] or '')[:110]}",
                      f"- cambio: `{str(e['valor_antes'])[:40]}` → `{str(e['valor_despues'])[:40]}`",
                      f"- **la citan {imp.get('n_citas', 0)} articulos del corpus**: "
                      f"{', '.join(imp.get('citada_por', [])[:12])}"
                      f"{' …' if len(imp.get('citada_por', [])) > 12 else ''}", ""]
                print(f"  ⚠️ {e['tipo_evento']:20} {nom:22} afecta a {imp.get('n_citas',0)} articulos")

        resto = [e for e in evs if e not in crit]
        if resto:
            L += ["## Resto de cambios", "", "| norma | evento | antes | despues |", "|---|---|---|---|"]
            for e in resto:
                L.append(f"| {e['id_norma']} | {e['tipo_evento']} | "
                         f"`{str(e['valor_antes'])[:26]}` | `{str(e['valor_despues'])[:26]}` |")

    out = Path("docs/monitor-ultimo-informe.md")
    out.write_text("\n".join(L) + "\n")
    print(f"escrito {out}")

    if marcar and evs:
        with with_connection() as c, c.cursor() as cur:
            cur.execute("UPDATE norma_evento SET notificado=true WHERE NOT notificado")
            c.commit()
        print(f"marcados {len(evs)} eventos como notificados")


if __name__ == "__main__":
    main(marcar="--marcar" in sys.argv, todos="--todos" in sys.argv)
