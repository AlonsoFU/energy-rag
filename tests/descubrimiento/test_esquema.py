"""T01 — esquema de norma_candidata y descubrimiento_corrida (H1-CA-11, 13, 40)."""
import datetime

import pytest
from psycopg.errors import CheckViolation, UniqueViolation
from psycopg.types.json import Jsonb

from scripts.descubrimiento_schema import crear_esquema
from src.storage.connection import with_connection


@pytest.fixture
def esquema(db_clean):
    """Crea las tablas y las vacia antes y despues (db_clean no las conoce)."""
    with with_connection() as conn:
        crear_esquema(conn)
        with conn.cursor() as cur:
            cur.execute("TRUNCATE norma_candidata, descubrimiento_corrida RESTART IDENTITY")
        conn.commit()
    yield
    with with_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("TRUNCATE norma_candidata, descubrimiento_corrida RESTART IDENTITY")
        conn.commit()


@pytest.mark.integration
def test_ddl_idempotente(esquema):
    with with_connection() as conn:
        crear_esquema(conn)
        crear_esquema(conn)


@pytest.mark.integration
def test_insertar_y_leer_candidata(esquema):
    with with_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """INSERT INTO norma_candidata
                   (id_norma, tipo, numero, titulo, organismos, organismo_normalizado,
                    fecha_publicacion, url, vias, afecta, estado, puntaje_dominio,
                    alcanza_corte, clase_dominio, relevante_por_vinculacion,
                    embedder, version_referencia)
                   VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
                ("1234", "DECRETO", "10", "Titulo de prueba", Jsonb(["Ministerio de Energia"]),
                 "energia", datetime.date(2026, 10, 1),
                 "https://www.bcn.cl/leychile/navegar?idNorma=1234",
                 Jsonb(["V", "O"]), Jsonb([{"id_norma": "99", "relacion": "modifica"}]),
                 "aprobada", 0.71, True, "en_dominio", True, "qwen3-embedding:4b", "v1"),
            )
            cur.execute(
                """SELECT id_norma, tipo, numero, titulo, organismos, organismo_normalizado,
                          fecha_publicacion, url, vias, afecta, estado, puntaje_dominio,
                          alcanza_corte, clase_dominio, relevante_por_vinculacion,
                          embedder, version_referencia, detectada_en
                   FROM norma_candidata WHERE id_norma = '1234'""")
            f = cur.fetchone()
        conn.commit()
    assert f[0:4] == ("1234", "DECRETO", "10", "Titulo de prueba")
    assert f[4] == ["Ministerio de Energia"]
    assert f[5] == "energia"
    assert f[6] == datetime.date(2026, 10, 1)
    assert f[7].endswith("idNorma=1234")
    assert f[8] == ["V", "O"]
    assert f[9] == [{"id_norma": "99", "relacion": "modifica"}]
    assert f[10] == "aprobada"
    assert f[11] == 0.71 and f[12] is True and f[13] == "en_dominio" and f[14] is True
    assert f[15] == "qwen3-embedding:4b" and f[16] == "v1"
    assert f[17] is not None


@pytest.mark.integration
def test_defaults_de_candidata(esquema):
    with with_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("INSERT INTO norma_candidata (id_norma) VALUES ('1')")
            cur.execute("""SELECT estado, vias, afecta, organismos, relevante_por_vinculacion,
                                  puntaje_dominio, alcanza_corte, clase_dominio
                           FROM norma_candidata""")
            f = cur.fetchone()
        conn.commit()
    assert f == ("pendiente", [], [], [], False, None, None, None)


@pytest.mark.integration
def test_estado_invalido_rechazado(esquema):
    with with_connection() as conn:
        with conn.cursor() as cur:
            with pytest.raises(CheckViolation):
                cur.execute("INSERT INTO norma_candidata (id_norma, estado) VALUES ('1','otro')")
        conn.rollback()


@pytest.mark.integration
def test_clase_dominio_invalida_rechazada(esquema):
    with with_connection() as conn:
        with conn.cursor() as cur:
            with pytest.raises(CheckViolation):
                cur.execute(
                    "INSERT INTO norma_candidata (id_norma, clase_dominio) VALUES ('1','x')")
        conn.rollback()


@pytest.mark.integration
def test_id_norma_duplicado_falla(esquema):
    with with_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("INSERT INTO norma_candidata (id_norma) VALUES ('1')")
            with pytest.raises(UniqueViolation):
                cur.execute("INSERT INTO norma_candidata (id_norma) VALUES ('1')")
        conn.rollback()


@pytest.mark.integration
def test_corrida_defaults(esquema):
    with with_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("INSERT INTO descubrimiento_corrida (ventana_desde) "
                        "VALUES ('2026-10-01') RETURNING id, exitosa, detalle, fin")
            f = cur.fetchone()
        conn.commit()
    assert f == (1, False, {}, None)
