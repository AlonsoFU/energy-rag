"""E4.1 — esquema del MAPA DE OBLIGACIONES (norma → obligación → proceso).

Es el foso: lo único que no se puede construir desde fuera del CEN. Un RAG legal responde
"¿qué dice el artículo X?"; esto responde **"¿qué me obliga a hacer, cuándo, y qué se rompe si
cambia?"**.

`obligacion` guarda, por artículo, la unidad accionable: QUIÉN debe hacer QUÉ, ANTE QUIÉN y en
QUÉ PLAZO. La extracción es del LLM local, pero **cada campo se valida contra el texto del
artículo** — si el sujeto no aparece literalmente en el artículo, la fila se descarta. Sin esa
validación el mapa sería una alucinación estructurada, que es peor que no tenerlo.

  PYTHONPATH=. venv/bin/python -m scripts.obligaciones_schema
"""
from src.components.vectorstore import with_connection

DDL = """
CREATE TABLE IF NOT EXISTS obligacion (
    id            bigserial PRIMARY KEY,
    articulo_id   bigint NOT NULL REFERENCES articulos(id) ON DELETE CASCADE,
    sujeto        text NOT NULL,           -- quien esta obligado
    accion        text NOT NULL,           -- que debe hacer
    destinatario  text,                    -- ante quien
    plazo         text,                    -- cuando / cada cuanto
    proceso       text,                    -- a que proceso del CEN pertenece
    evidencia     text NOT NULL,           -- fragmento literal que la sostiene
    validada      boolean NOT NULL DEFAULT false,
    extraido_en   timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS ix_obligacion_art     ON obligacion (articulo_id);
CREATE INDEX IF NOT EXISTS ix_obligacion_sujeto  ON obligacion (lower(sujeto));
CREATE INDEX IF NOT EXISTS ix_obligacion_proceso ON obligacion (proceso);

-- una misma obligacion no se duplica al re-extraer
CREATE UNIQUE INDEX IF NOT EXISTS ux_obligacion
    ON obligacion (articulo_id, lower(sujeto), left(lower(accion), 120));
"""


def main():
    with with_connection() as c, c.cursor() as cur:
        cur.execute(DDL)
        c.commit()
        cur.execute("SELECT count(*) FROM obligacion")
        print(f"ok — tabla obligacion ({cur.fetchone()[0]} filas)")


if __name__ == "__main__":
    main()
