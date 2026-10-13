"""H1 — esquema del descubrimiento de normas nuevas (idempotente).

Crea dos tablas:
  norma_candidata          una fila por norma nueva reconocida en BCN
  descubrimiento_corrida   una fila por corrida del descubrimiento

No toca `normas` ni `articulos`. Contrato: docs/briefs/contrato.md, seccion 4.

  PYTHONPATH=. venv/bin/python -m scripts.descubrimiento_schema
"""
from src.storage.connection import with_connection

DDL = """
CREATE TABLE IF NOT EXISTS norma_candidata (
    id_norma                  text PRIMARY KEY,
    tipo                      text,
    numero                    text,
    titulo                    text,
    organismos                jsonb NOT NULL DEFAULT '[]'::jsonb,
    organismo_normalizado     text,
    fecha_publicacion         date,
    url                       text,
    vias                      jsonb NOT NULL DEFAULT '[]'::jsonb,
    afecta                    jsonb NOT NULL DEFAULT '[]'::jsonb,
    estado                    text NOT NULL DEFAULT 'pendiente' CHECK (estado IN (
                                  'pendiente','aprobada','rechazada','fallo_identidad')),
    puntaje_dominio           double precision,
    alcanza_corte             boolean,
    clase_dominio             text CHECK (clase_dominio IS NULL OR clase_dominio IN (
                                  'en_dominio','dudosa','fuera_de_dominio')),
    relevante_por_vinculacion boolean NOT NULL DEFAULT false,
    embedder                  text,
    version_referencia        text,
    detectada_en              timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS ix_norma_candidata_estado ON norma_candidata (estado);

CREATE TABLE IF NOT EXISTS descubrimiento_corrida (
    id            bigserial PRIMARY KEY,
    inicio        timestamptz NOT NULL DEFAULT now(),
    fin           timestamptz,
    ventana_desde date,
    ventana_hasta date,
    exitosa       boolean NOT NULL DEFAULT false,
    detalle       jsonb NOT NULL DEFAULT '{}'::jsonb
);
CREATE INDEX IF NOT EXISTS ix_descubrimiento_corrida_inicio
    ON descubrimiento_corrida (inicio DESC);
"""


def crear_esquema(conn):
    """Ejecuta el DDL (idempotente) con la conexion dada y hace commit."""
    with conn.cursor() as cur:
        cur.execute(DDL)
    conn.commit()


def main():
    with with_connection() as c:
        crear_esquema(c)
        with c.cursor() as cur:
            cur.execute("SELECT count(*) FROM norma_candidata")
            cand = cur.fetchone()[0]
            cur.execute("SELECT count(*) FROM descubrimiento_corrida")
            corr = cur.fetchone()[0]
    print(f"ok — norma_candidata ({cand} filas) · descubrimiento_corrida ({corr} filas)")


if __name__ == "__main__":
    main()
