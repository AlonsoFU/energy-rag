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

    @staticmethod
    def _filtro_dominio() -> str:
        """Fragmento SQL que excluye las normas marcadas fuera del dominio.

        La frontera (decidida por el usuario 2026-08-22: "todo lo referente a la subgerencia
        de mercados") marca `normas.metadata.fuera_de_dominio`. **Marcar no basta**: sin este
        filtro los 1352 fragmentos ajenos siguen entrando al pool y compitiendo. Se aplica en
        BM25 y en el KNN denso, que son las dos patas del retrieval.

        Flag `filtrar_fuera_dominio` (default OFF hasta medir). Devuelve "" si esta apagado,
        asi que el SQL queda identico al de antes cuando no se usa.
        """
        from src.core import config as _cfg
        if not getattr(_cfg.settings, "filtrar_fuera_dominio", False):
            return ""
        sql = (" AND NOT coalesce((SELECT (n2.metadata->>'fuera_de_dominio')='true' "
               "FROM normas n2 WHERE n2.id_norma = a.id_norma), false)")
        # Articulos DUPLICADOS: una ley modificatoria guardo como suyos los articulos que
        # inserta en otro cuerpo legal. LEY 20936 tiene 55 articulos (72°-122°, 212°) que
        # pertenecen al DFL 4 y estan tambien alli, mejor numerados. Sin este filtro el
        # sistema puede responder "[LEY 20936 art 92°]" cuando la cita correcta es
        # "[DFL 4 art 92°]" -- una cita FALSA, que es el peor error en un sistema legal.
        # Se excluye el duplicado, no el original: `duplicado_de` apunta al que se conserva.
        if getattr(_cfg.settings, "filtrar_duplicados", True):
            sql += " AND (a.metadata->>'duplicado_de') IS NULL"
        return sql

    def search_bm25(self, query: str, top_k: int = 50) -> list[dict]:
        # bm25_doc2query (flag): busca sobre tsv_aug (contextual_text + preguntas
        # doc2query generadas) en vez de tsv. "Despierta" BM25 para fraseo
        # coloquial sin tocar el reranker (que sigue usando contextual_text).
        # Cae a tsv si la columna no existe (corpus sin expandir).
        from src.core import config as _cfg
        col = "tsv"
        if getattr(_cfg.settings, "bm25_doc2query", False):
            with with_connection() as conn, conn.cursor() as _c:
                _c.execute("SELECT 1 FROM information_schema.columns "
                           "WHERE table_name='fragmentos' AND column_name='tsv_aug'")
                if _c.fetchone():
                    col = "tsv_aug"
        with with_connection() as conn, conn.cursor(row_factory=dict_row) as cur:
            dom = self._filtro_dominio()
            cur.execute(f"""
                SELECT f.id, f.articulo_id, f.text, f.contextual_text,
                       a.id_norma, a.numero AS articulo_numero,
                       ts_rank_cd(f.{col}, plainto_tsquery('spanish', %s)) AS score
                FROM fragmentos f
                JOIN articulos a ON a.id = f.articulo_id
                WHERE f.{col} @@ plainto_tsquery('spanish', %s) {dom}
                ORDER BY score DESC
                LIMIT %s
            """, (query, query, top_k))
            return cur.fetchall()

    def search_vector_bgem3(self, query_embedding: list[float], top_k: int = 50) -> list[dict]:
        """Búsqueda densa sobre la columna embedding_bgem3 (2do embedder del ensemble).
        Devuelve [] si la columna no existe o está vacía (corpus sin embeber con bge-m3)."""
        with with_connection() as conn, conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                "SELECT 1 FROM information_schema.columns "
                "WHERE table_name='fragmentos' AND column_name='embedding_bgem3'")
            if not cur.fetchone():
                return []
            cur.execute("""
                SELECT f.id, f.articulo_id, f.text, f.contextual_text,
                       a.id_norma, a.numero AS articulo_numero,
                       1 - (f.embedding_bgem3 <=> %s::vector) AS score
                FROM fragmentos f
                JOIN articulos a ON a.id = f.articulo_id
                WHERE f.embedding_bgem3 IS NOT NULL
                ORDER BY f.embedding_bgem3 <=> %s::vector
                LIMIT %s
            """, (query_embedding, query_embedding, top_k))
            return cur.fetchall()

    def search_vector_4b(self, query_embedding: list[float], top_k: int = 50) -> list[dict]:
        """KNN exacto sobre embedding_4b (Qwen3-Embedding-4B, 2560-dim, GGUF Ollama).
        Sin índice ANN (pgvector no indexa >2000 dim) → seq scan exacto, OK en ~3900 filas.
        Devuelve [] si la columna no existe o está vacía."""
        with with_connection() as conn, conn.cursor(row_factory=dict_row) as cur:
            cur.execute("SELECT 1 FROM information_schema.columns "
                        "WHERE table_name='fragmentos' AND column_name='embedding_4b'")
            if not cur.fetchone():
                return []
            cur.execute("""
                SELECT f.id, f.articulo_id, f.text, f.contextual_text,
                       a.id_norma, a.numero AS articulo_numero,
                       1 - (f.embedding_4b <=> %s::vector) AS score
                FROM fragmentos f
                JOIN articulos a ON a.id = f.articulo_id
                WHERE f.embedding_4b IS NOT NULL
                ORDER BY f.embedding_4b <=> %s::vector
                LIMIT %s
            """, (query_embedding, query_embedding, top_k))
            return cur.fetchall()

    def search_vector_4b_1024(self, query_embedding: list[float], top_k: int = 50,
                              exclude_glossary: bool = False) -> list[dict]:
        """KNN sobre embedding_4b_1024 (MRL prefix 1024-dim, indexable HNSW). Query debe
        venir ya truncada a 1024 + renormalizada. [] si la columna no existe.
        exclude_glossary: parte del rechunk M2 — saca los chunks-glosario gigantes (re-fragmentados
        en fragmentos_definicion) para que el def-fragment los REEMPLACE. Se gatea por-query (solo
        queries de definición) desde _vector_4b_search, no global."""
        with with_connection() as conn, conn.cursor(row_factory=dict_row) as cur:
            cur.execute("SELECT 1 FROM information_schema.columns "
                        "WHERE table_name='fragmentos' AND column_name='embedding_4b_1024'")
            if not cur.fetchone():
                return []
            dom = self._filtro_dominio()
            excl = ""
            if exclude_glossary:
                excl = "AND f.articulo_id NOT IN (SELECT DISTINCT articulo_id FROM fragmentos_definicion)"
            cur.execute(f"""
                SELECT f.id, f.articulo_id, f.text, f.contextual_text,
                       a.id_norma, a.numero AS articulo_numero,
                       1 - (f.embedding_4b_1024 <=> %s::vector) AS score
                FROM fragmentos f JOIN articulos a ON a.id = f.articulo_id
                WHERE f.embedding_4b_1024 IS NOT NULL {excl} {dom}
                ORDER BY f.embedding_4b_1024 <=> %s::vector
                LIMIT %s
            """, (query_embedding, query_embedding, top_k))
            return cur.fetchall()

    def glossary_terms(self) -> list[str]:
        """Todos los terminos del glosario. Alimenta `glossary_lookup` (extraccion del termino
        por diccionario en vez de por regex de prefijo). [] si la tabla no existe."""
        with with_connection() as conn, conn.cursor(row_factory=dict_row) as cur:
            cur.execute("SELECT 1 FROM information_schema.tables WHERE table_name='fragmentos_definicion'")
            if not cur.fetchone():
                return []
            cur.execute("SELECT DISTINCT termino FROM fragmentos_definicion WHERE termino IS NOT NULL")
            return [r["termino"] for r in cur.fetchall()]

    def def_exact_all(self, concepto: str) -> list[dict]:
        """TODAS las definiciones del termino, una por norma. Base de D4 (ambiguedad).

        `def_exact` devuelve UNA sola y desempata con `ORDER BY length(texto) DESC`, criterio
        arbitrario. 35 terminos del glosario estan definidos en mas de una norma; cuando el
        usuario pregunta por uno de ellos, el sistema hoy AFIRMA una acepcion sin avisar que
        hay otras. Medido en 'que es la comision' y 'que significa coordinado'.
        """
        with with_connection() as conn, conn.cursor(row_factory=dict_row) as cur:
            cur.execute("SELECT 1 FROM information_schema.tables WHERE table_name='fragmentos_definicion'")
            if not cur.fetchone():
                return []
            cur.execute("""
                SELECT DISTINCT ON (a.id_norma)
                       (900000000 + fd.id) AS id, fd.articulo_id, fd.texto AS text,
                       fd.texto AS contextual_text, a.id_norma, a.numero AS articulo_numero,
                       n.tipo, n.numero AS norma_numero
                FROM fragmentos_definicion fd
                JOIN articulos a ON a.id = fd.articulo_id
                JOIN normas n ON n.id_norma = a.id_norma
                WHERE lower(fd.termino) = lower(%s)
                ORDER BY a.id_norma, length(fd.texto) DESC
            """, (concepto,))
            return cur.fetchall()

    def def_exact(self, concepto: str) -> dict | None:
        """glossary_inject: match EXACTO concepto→def-fragment (case-insensitive). Devuelve un
        doc del artículo padre (parent-doc) o None. Determinista, alta precisión (no como el RRF
        de def_fragments que desplazaba). id con offset 9e8 para no colisionar."""
        with with_connection() as conn, conn.cursor(row_factory=dict_row) as cur:
            cur.execute("SELECT 1 FROM information_schema.tables WHERE table_name='fragmentos_definicion'")
            if not cur.fetchone():
                return None
            cur.execute("""
                SELECT (900000000 + fd.id) AS id, fd.articulo_id, fd.texto AS text,
                       fd.texto AS contextual_text, a.id_norma, a.numero AS articulo_numero
                FROM fragmentos_definicion fd JOIN articulos a ON a.id = fd.articulo_id
                WHERE lower(fd.termino) = lower(%s)
                ORDER BY length(fd.texto) DESC LIMIT 1
            """, (concepto,))
            return cur.fetchone()

    def search_vector_def_4b_1024(self, query_embedding: list[float], top_k: int = 50) -> list[dict]:
        """M2 (def_fragments): KNN sobre fragmentos_definicion (1 def = 1 fragmento, MRL-1024).
        Mapea al ARTICULO PADRE (parent-doc) para que la cita sea [Art N de NORMA]. El text
        devuelto es la definicion focalizada (mejor para rerank/gen que el glosario gigante).
        id con offset 9e8 para no colisionar con fragmentos.id. [] si la tabla no existe."""
        with with_connection() as conn, conn.cursor(row_factory=dict_row) as cur:
            cur.execute("SELECT 1 FROM information_schema.tables WHERE table_name='fragmentos_definicion'")
            if not cur.fetchone():
                return []
            cur.execute("""
                SELECT (900000000 + fd.id) AS id, fd.articulo_id, fd.texto AS text,
                       fd.texto AS contextual_text, a.id_norma, a.numero AS articulo_numero,
                       1 - (fd.embedding_4b_1024 <=> %s::vector) AS score
                FROM fragmentos_definicion fd JOIN articulos a ON a.id = fd.articulo_id
                WHERE fd.embedding_4b_1024 IS NOT NULL
                ORDER BY fd.embedding_4b_1024 <=> %s::vector
                LIMIT %s
            """, (query_embedding, query_embedding, top_k))
            return cur.fetchall()

    def search_vector_8b(self, query_embedding: list[float], top_k: int = 50) -> list[dict]:
        """KNN exacto sobre embedding_8b (Qwen3-Embedding-8B, 4096-dim, GGUF Ollama).
        Sin índice ANN (>2000 dim) → seq scan exacto. [] si la columna no existe."""
        with with_connection() as conn, conn.cursor(row_factory=dict_row) as cur:
            cur.execute("SELECT 1 FROM information_schema.columns "
                        "WHERE table_name='fragmentos' AND column_name='embedding_8b'")
            if not cur.fetchone():
                return []
            cur.execute("""
                SELECT f.id, f.articulo_id, f.text, f.contextual_text,
                       a.id_norma, a.numero AS articulo_numero,
                       1 - (f.embedding_8b <=> %s::vector) AS score
                FROM fragmentos f JOIN articulos a ON a.id = f.articulo_id
                WHERE f.embedding_8b IS NOT NULL
                ORDER BY f.embedding_8b <=> %s::vector
                LIMIT %s
            """, (query_embedding, query_embedding, top_k))
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
