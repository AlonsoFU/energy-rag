"""B4.1 — esquema del MONITOR de cambios normativos (idempotente).

Crea `norma_evento`: la bitacora de todo cambio detectado en el corpus. Es la base de E5
(monitorear), que es lo que el proyecto pide de verdad: *"el 04.11.2024 la ley 21711 derogo el
art. 23 del decreto X, que tu sistema citaba"*.

Tipos de evento (enum abierto por CHECK, se amplia cuando aparezca uno nuevo):
  norma_nueva          aparecio una norma que el corpus no tenia
  texto_modificado     cambio el `content_hash` del texto guardado
  version_nueva        BCN publico una version nueva (metadata.versiones crecio)
  estado_cambiado      cambio metadata.estado (ej. vigente -> derogado)
  vinculacion_nueva    apareció una arista norma->norma que no estaba
  articulo_derogado    se marco un articulo como derogado

`impacto` guarda a que se ve afectado el sistema: los articulos del corpus que CITAN la norma
que cambio (se calcula con `referencias.tipo_relacion='remite'`, poblado por B3.4). Sin eso el
monitor avisa "cambio algo" y no sirve; con eso avisa "cambio algo QUE TU CITAS".

  PYTHONPATH=. venv/bin/python -m scripts.monitor_schema
"""
from src.components.vectorstore import with_connection

DDL = """
CREATE TABLE IF NOT EXISTS norma_evento (
    id            bigserial PRIMARY KEY,
    id_norma      text NOT NULL,
    tipo_evento   text NOT NULL CHECK (tipo_evento IN (
                      'norma_nueva','texto_modificado','version_nueva',
                      'estado_cambiado','vinculacion_nueva','articulo_derogado')),
    detectado_en  timestamptz NOT NULL DEFAULT now(),
    fecha_evento  date,
    valor_antes   text,
    valor_despues text,
    detalle       jsonb NOT NULL DEFAULT '{}'::jsonb,
    impacto       jsonb NOT NULL DEFAULT '{}'::jsonb,
    notificado    boolean NOT NULL DEFAULT false
);
CREATE INDEX IF NOT EXISTS ix_norma_evento_norma  ON norma_evento (id_norma);
CREATE INDEX IF NOT EXISTS ix_norma_evento_fecha  ON norma_evento (detectado_en DESC);
CREATE INDEX IF NOT EXISTS ix_norma_evento_pend   ON norma_evento (notificado) WHERE NOT notificado;

-- una norma no puede tener dos veces el MISMO cambio con el mismo valor: el monitor corre
-- periodicamente y sin esto duplicaria un evento en cada pasada.
CREATE UNIQUE INDEX IF NOT EXISTS ux_norma_evento_dedup
    ON norma_evento (id_norma, tipo_evento, coalesce(valor_despues,''));

-- snapshot del ultimo estado conocido, para poder diffear sin depender de que `normas`
-- ya haya sido sobrescrita por el crawler.
CREATE TABLE IF NOT EXISTS norma_snapshot (
    id_norma      text PRIMARY KEY,
    content_hash  text,
    estado        text,
    n_versiones   integer,
    n_articulos   integer,
    vinculaciones jsonb NOT NULL DEFAULT '[]'::jsonb,
    tomado_en     timestamptz NOT NULL DEFAULT now()
);
"""


def main():
    with with_connection() as c, c.cursor() as cur:
        cur.execute(DDL)
        c.commit()
        cur.execute("SELECT count(*) FROM norma_evento")
        ev = cur.fetchone()[0]
        cur.execute("SELECT count(*) FROM norma_snapshot")
        sn = cur.fetchone()[0]
    print(f"ok — norma_evento ({ev} filas) · norma_snapshot ({sn} filas)")


if __name__ == "__main__":
    main()
