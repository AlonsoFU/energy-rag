"""initial schema

Revision ID: 0001
Revises:
Create Date: 2026-04-26
"""
from alembic import op

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None

def upgrade():
    op.execute("CREATE EXTENSION IF NOT EXISTS vector;")
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm;")

    op.execute("""
    CREATE OR REPLACE FUNCTION trg_set_updated_at()
    RETURNS TRIGGER AS $$
    BEGIN NEW.updated_at = now(); RETURN NEW; END;
    $$ LANGUAGE plpgsql;
    """)

    op.execute("""
    CREATE TABLE normas (
        id_norma          TEXT PRIMARY KEY,
        tipo              TEXT NOT NULL,
        numero            TEXT NOT NULL,
        titulo            TEXT NOT NULL,
        fecha_publicacion DATE,
        organismo         TEXT,
        clase             TEXT,
        texto_completo    TEXT,
        metadata          JSONB,
        fetched_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
        created_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
        updated_at        TIMESTAMPTZ NOT NULL DEFAULT now()
    );
    CREATE INDEX idx_normas_tipo_clase ON normas(tipo, clase);
    CREATE INDEX idx_normas_fecha ON normas(fecha_publicacion DESC);
    CREATE TRIGGER trg_normas_updated BEFORE UPDATE ON normas
      FOR EACH ROW EXECUTE FUNCTION trg_set_updated_at();
    """)

    op.execute("""
    CREATE TABLE articulos (
        id          BIGSERIAL PRIMARY KEY,
        id_norma    TEXT NOT NULL REFERENCES normas(id_norma) ON DELETE CASCADE,
        numero      TEXT NOT NULL,
        titulo      TEXT,
        texto       TEXT NOT NULL,
        orden       INT,
        metadata    JSONB,
        created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
        updated_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
        UNIQUE (id_norma, numero)
    );
    CREATE INDEX idx_articulos_norma ON articulos(id_norma);
    CREATE TRIGGER trg_articulos_updated BEFORE UPDATE ON articulos
      FOR EACH ROW EXECUTE FUNCTION trg_set_updated_at();
    """)

    op.execute("""
    CREATE TABLE fragmentos (
        id              BIGSERIAL PRIMARY KEY,
        articulo_id     BIGINT NOT NULL REFERENCES articulos(id) ON DELETE CASCADE,
        chunk_index     INT NOT NULL,
        text            TEXT NOT NULL,
        contextual_text TEXT NOT NULL,
        embedding       vector(768),
        tsv             tsvector
                        GENERATED ALWAYS AS (to_tsvector('spanish', contextual_text)) STORED,
        token_count     INT,
        metadata        JSONB,
        created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
        updated_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
        UNIQUE (articulo_id, chunk_index)
    );
    CREATE INDEX idx_fragmentos_embedding ON fragmentos USING hnsw (embedding vector_cosine_ops);
    CREATE INDEX idx_fragmentos_tsv ON fragmentos USING gin (tsv);
    CREATE INDEX idx_fragmentos_articulo ON fragmentos(articulo_id);
    CREATE TRIGGER trg_fragmentos_updated BEFORE UPDATE ON fragmentos
      FOR EACH ROW EXECUTE FUNCTION trg_set_updated_at();
    """)

    op.execute("""
    CREATE TABLE conceptos (
        id          BIGSERIAL PRIMARY KEY,
        nombre      TEXT NOT NULL UNIQUE,
        definicion  TEXT,
        aliases     TEXT[],
        metadata    JSONB,
        created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
        updated_at  TIMESTAMPTZ NOT NULL DEFAULT now()
    );
    CREATE TRIGGER trg_conceptos_updated BEFORE UPDATE ON conceptos
      FOR EACH ROW EXECUTE FUNCTION trg_set_updated_at();
    """)

    op.execute("""
    CREATE TABLE referencias (
        id                  BIGSERIAL PRIMARY KEY,
        origen_articulo_id  BIGINT REFERENCES articulos(id)        ON DELETE CASCADE,
        origen_norma_id     TEXT   REFERENCES normas(id_norma)     ON DELETE CASCADE,
        destino_articulo_id BIGINT REFERENCES articulos(id)        ON DELETE CASCADE,
        destino_norma_id    TEXT   REFERENCES normas(id_norma)     ON DELETE CASCADE,
        destino_concepto_id BIGINT REFERENCES conceptos(id)        ON DELETE CASCADE,
        tipo_relacion       TEXT NOT NULL CHECK (tipo_relacion IN
                            ('cita','remite','aplica','modifica','deroga',
                             'complementa','define_termino','referencia_implicita')),
        confianza           REAL CHECK (confianza BETWEEN 0 AND 1),
        metodo_extraccion   TEXT NOT NULL CHECK (metodo_extraccion IN ('regex','llm','manual')),
        destino_subdivision TEXT,
        contexto            TEXT,
        metadata            JSONB,
        created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
        CHECK ((origen_articulo_id IS NOT NULL)::int +
               (origen_norma_id IS NOT NULL)::int = 1),
        CHECK ((destino_articulo_id IS NOT NULL)::int +
               (destino_norma_id IS NOT NULL)::int +
               (destino_concepto_id IS NOT NULL)::int = 1)
    );
    CREATE INDEX idx_ref_origen_art   ON referencias(origen_articulo_id);
    CREATE INDEX idx_ref_origen_norm  ON referencias(origen_norma_id);
    CREATE INDEX idx_ref_destino_art  ON referencias(destino_articulo_id);
    CREATE INDEX idx_ref_destino_norm ON referencias(destino_norma_id);
    CREATE INDEX idx_ref_destino_conc ON referencias(destino_concepto_id);
    """)

    op.execute("""
    CREATE TABLE consultas_log (
        id              BIGSERIAL PRIMARY KEY,
        ts              TIMESTAMPTZ NOT NULL DEFAULT now(),
        query           TEXT NOT NULL,
        branch          TEXT NOT NULL CHECK (branch IN ('simple','complejo')),
        n_results       INT,
        latency_ms      INT,
        rerank_ms       INT,
        generation_ms   INT,
        llm_model       TEXT,
        llm_tokens_in   INT,
        llm_tokens_out  INT,
        grounding_pass  BOOLEAN,
        metadata        JSONB
    );
    CREATE INDEX idx_consultas_log_ts ON consultas_log(ts DESC);
    """)

    op.execute("""
    CREATE TABLE descargas_estado (
        id_norma      TEXT PRIMARY KEY,
        estado        TEXT NOT NULL CHECK (estado IN ('pending','downloaded','failed','outdated')),
        intentos      INT NOT NULL DEFAULT 0,
        last_attempt  TIMESTAMPTZ,
        last_error    TEXT,
        bcn_hash      TEXT,
        created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
        updated_at    TIMESTAMPTZ NOT NULL DEFAULT now()
    );
    CREATE INDEX idx_descargas_estado ON descargas_estado(estado);
    CREATE TRIGGER trg_descargas_updated BEFORE UPDATE ON descargas_estado
      FOR EACH ROW EXECUTE FUNCTION trg_set_updated_at();
    """)

    op.execute("""
    CREATE TABLE aliases_aprendidos (
        id              BIGSERIAL PRIMARY KEY,
        alias_text      TEXT NOT NULL,
        id_norma        TEXT NOT NULL REFERENCES normas(id_norma) ON DELETE CASCADE,
        confianza       REAL CHECK (confianza BETWEEN 0 AND 1),
        fuente          TEXT NOT NULL,
        aprobado        BOOLEAN NOT NULL DEFAULT false,
        created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
        UNIQUE (alias_text, id_norma)
    );
    """)

    op.execute("""
    CREATE VIEW norma_norma AS
    SELECT DISTINCT
        COALESCE(a1.id_norma, r.origen_norma_id) AS origen,
        COALESCE(a2.id_norma, r.destino_norma_id) AS destino,
        r.tipo_relacion
    FROM referencias r
    LEFT JOIN articulos a1 ON a1.id = r.origen_articulo_id
    LEFT JOIN articulos a2 ON a2.id = r.destino_articulo_id
    WHERE COALESCE(a2.id_norma, r.destino_norma_id) IS NOT NULL;
    """)

    op.execute("""
    CREATE VIEW norma_concepto AS
    SELECT DISTINCT
        COALESCE(a1.id_norma, r.origen_norma_id) AS id_norma,
        r.destino_concepto_id AS concepto_id,
        r.tipo_relacion AS relacion
    FROM referencias r
    LEFT JOIN articulos a1 ON a1.id = r.origen_articulo_id
    WHERE r.destino_concepto_id IS NOT NULL;
    """)

def downgrade():
    op.execute("DROP VIEW IF EXISTS norma_concepto;")
    op.execute("DROP VIEW IF EXISTS norma_norma;")
    op.execute("DROP TABLE IF EXISTS aliases_aprendidos;")
    op.execute("DROP TABLE IF EXISTS descargas_estado;")
    op.execute("DROP TABLE IF EXISTS consultas_log;")
    op.execute("DROP TABLE IF EXISTS referencias;")
    op.execute("DROP TABLE IF EXISTS conceptos;")
    op.execute("DROP TABLE IF EXISTS fragmentos;")
    op.execute("DROP TABLE IF EXISTS articulos;")
    op.execute("DROP TABLE IF EXISTS normas;")
    op.execute("DROP FUNCTION IF EXISTS trg_set_updated_at;")
