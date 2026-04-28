import json
from psycopg.rows import dict_row
from src.storage.connection import with_connection
from src.core.models import Norma, Articulo, Fragmento, Concepto, Referencia


class PostgresStore:
    """Repository for normas, articulos, fragmentos, conceptos, referencias.
    Provides BM25 + vector search."""

    # ---------- NORMAS ----------
    def upsert_norma(self, n: Norma) -> None:
        with with_connection() as conn, conn.cursor() as cur:
            cur.execute("""
                INSERT INTO normas (id_norma, tipo, numero, titulo, fecha_publicacion,
                                    organismo, clase, texto_completo, metadata)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s::jsonb)
                ON CONFLICT (id_norma) DO UPDATE SET
                  tipo=EXCLUDED.tipo, numero=EXCLUDED.numero, titulo=EXCLUDED.titulo,
                  fecha_publicacion=EXCLUDED.fecha_publicacion, organismo=EXCLUDED.organismo,
                  clase=EXCLUDED.clase, texto_completo=EXCLUDED.texto_completo,
                  metadata=EXCLUDED.metadata
            """, (n.id_norma, n.tipo, n.numero, n.titulo, n.fecha_publicacion,
                  n.organismo, n.clase, n.texto_completo, json.dumps(n.metadata)))
            conn.commit()

    def get_norma(self, id_norma: str) -> Norma | None:
        with with_connection() as conn, conn.cursor(row_factory=dict_row) as cur:
            cur.execute("SELECT * FROM normas WHERE id_norma=%s", (id_norma,))
            row = cur.fetchone()
            if not row:
                return None
            return Norma(**{k: v for k, v in row.items() if k in Norma.model_fields})

    # ---------- ARTICULOS ----------
    def upsert_articulo(self, a: Articulo) -> int:
        with with_connection() as conn, conn.cursor() as cur:
            cur.execute("""
                INSERT INTO articulos (id_norma, numero, titulo, texto, orden, metadata)
                VALUES (%s,%s,%s,%s,%s,%s::jsonb)
                ON CONFLICT (id_norma, numero) DO UPDATE SET
                  titulo=EXCLUDED.titulo, texto=EXCLUDED.texto,
                  orden=EXCLUDED.orden, metadata=EXCLUDED.metadata
                RETURNING id
            """, (a.id_norma, a.numero, a.titulo, a.texto, a.orden, json.dumps(a.metadata)))
            (art_id,) = cur.fetchone()
            conn.commit()
            return art_id

    def get_articulo(self, articulo_id: int) -> dict | None:
        with with_connection() as conn, conn.cursor(row_factory=dict_row) as cur:
            cur.execute("SELECT * FROM articulos WHERE id=%s", (articulo_id,))
            return cur.fetchone()

    # ---------- FRAGMENTOS ----------
    def upsert_fragmento(self, f: Fragmento) -> int:
        with with_connection() as conn, conn.cursor() as cur:
            cur.execute("""
                INSERT INTO fragmentos
                  (articulo_id, chunk_index, text, contextual_text, embedding,
                   token_count, metadata)
                VALUES (%s,%s,%s,%s,%s,%s,%s::jsonb)
                ON CONFLICT (articulo_id, chunk_index) DO UPDATE SET
                  text=EXCLUDED.text, contextual_text=EXCLUDED.contextual_text,
                  embedding=EXCLUDED.embedding, token_count=EXCLUDED.token_count,
                  metadata=EXCLUDED.metadata
                RETURNING id
            """, (f.articulo_id, f.chunk_index, f.text, f.contextual_text,
                  f.embedding, f.token_count, json.dumps(f.metadata)))
            (fid,) = cur.fetchone()
            conn.commit()
            return fid

    def search_vector(self, query_embedding: list[float], top_k: int = 50) -> list[dict]:
        with with_connection() as conn, conn.cursor(row_factory=dict_row) as cur:
            cur.execute("""
                SELECT f.id, f.articulo_id, f.text, f.contextual_text,
                       a.id_norma, a.numero AS articulo_numero,
                       1 - (f.embedding <=> %s::vector) AS score
                FROM fragmentos f
                JOIN articulos a ON a.id = f.articulo_id
                ORDER BY f.embedding <=> %s::vector
                LIMIT %s
            """, (query_embedding, query_embedding, top_k))
            return cur.fetchall()

    def search_bm25(self, query: str, top_k: int = 50) -> list[dict]:
        with with_connection() as conn, conn.cursor(row_factory=dict_row) as cur:
            cur.execute("""
                SELECT f.id, f.articulo_id, f.text, f.contextual_text,
                       a.id_norma, a.numero AS articulo_numero,
                       ts_rank_cd(f.tsv, plainto_tsquery('spanish', %s)) AS score
                FROM fragmentos f
                JOIN articulos a ON a.id = f.articulo_id
                WHERE f.tsv @@ plainto_tsquery('spanish', %s)
                ORDER BY score DESC
                LIMIT %s
            """, (query, query, top_k))
            return cur.fetchall()

    # ---------- CONCEPTOS ----------
    def upsert_concepto(self, c: Concepto) -> int:
        with with_connection() as conn, conn.cursor() as cur:
            cur.execute("""
                INSERT INTO conceptos (nombre, definicion, aliases, metadata)
                VALUES (%s,%s,%s,%s::jsonb)
                ON CONFLICT (nombre) DO UPDATE SET
                  definicion=EXCLUDED.definicion, aliases=EXCLUDED.aliases,
                  metadata=EXCLUDED.metadata
                RETURNING id
            """, (c.nombre, c.definicion, c.aliases, json.dumps(c.metadata)))
            (cid,) = cur.fetchone()
            conn.commit()
            return cid

    # ---------- REFERENCIAS ----------
    def upsert_referencia(self, r: Referencia) -> int:
        with with_connection() as conn, conn.cursor() as cur:
            cur.execute("""
                INSERT INTO referencias
                  (origen_articulo_id, origen_norma_id,
                   destino_articulo_id, destino_norma_id, destino_concepto_id,
                   tipo_relacion, confianza, metodo_extraccion,
                   destino_subdivision, contexto, metadata)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s::jsonb)
                RETURNING id
            """, (r.origen_articulo_id, r.origen_norma_id,
                  r.destino_articulo_id, r.destino_norma_id, r.destino_concepto_id,
                  r.tipo_relacion, r.confianza, r.metodo_extraccion,
                  r.destino_subdivision, r.contexto, json.dumps(r.metadata)))
            (rid,) = cur.fetchone()
            conn.commit()
            return rid

    # ---------- CATALOG SUPPORT ----------
    def list_normas_for_catalogo(self) -> list[dict]:
        with with_connection() as conn, conn.cursor(row_factory=dict_row) as cur:
            cur.execute("SELECT id_norma, tipo, numero, titulo, fecha_publicacion FROM normas")
            rows = cur.fetchall()
            for r in rows:
                if r.get("fecha_publicacion"):
                    r["año"] = r["fecha_publicacion"].year
            return rows
