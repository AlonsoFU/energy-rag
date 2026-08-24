"""FASE 1.3 — que una consulta no se pierda porque un servicio se cayó a mitad de camino.

Problema real, no hipotético: el container `energy_rag_pg` **se apaga solo** (documentado en
CLAUDE.md). Los chequeos previos de `preguntar.py` corren ANTES de cargar modelos; si Postgres
muere durante el retrieval —40 s después— el usuario pierde la consulta entera y ve un
stacktrace.

**Se clasifica por CLASE de excepción, no por el texto del error.** Un `OperationalError` es
transitorio por definición del driver; un `KeyError` en el parser es un bug y reintentarlo tres
veces solo tarda tres veces más en fallar. Leer el mensaje con un regex para adivinar cuál es
cuál sería exactamente el mecanismo que este proyecto no usa: la jerarquía de excepciones ya
trae la clasificación hecha por quien escribió el driver.

Ollama ya reintenta adentro (`llm.py`: 3 intentos ante Timeout/ConnectionError) y agota
devolviendo texto VACÍO en vez de excepción — por eso `respuesta_vacia()` existe aparte: es un
fallo que no llega como error y hay que cazarlo mirando el resultado.
"""
from __future__ import annotations

import subprocess
import time
from typing import Callable, TypeVar

T = TypeVar("T")

# Clases transitorias. Se importan perezosamente para no atar este módulo a que psycopg o
# requests estén instalados en cualquier contexto que lo importe (los scripts de crawling
# no cargan la DB).
_TRANSITORIAS: tuple[type[BaseException], ...] | None = None


def transitorias() -> tuple[type[BaseException], ...]:
    global _TRANSITORIAS
    if _TRANSITORIAS is None:
        # ConnectionError y TimeoutError, NO `OSError` a secas: FileNotFoundError tambien
        # es OSError y reintentar un archivo que no existe solo tarda 3x en fallar.
        clases: list[type[BaseException]] = [ConnectionError, TimeoutError]
        try:
            import psycopg
            clases.append(psycopg.OperationalError)
        except Exception:
            pass
        try:
            from psycopg_pool import PoolTimeout
            clases.append(PoolTimeout)
        except Exception:
            pass
        try:
            import requests
            clases += [requests.exceptions.ConnectionError, requests.exceptions.Timeout]
        except Exception:
            pass
        _TRANSITORIAS = tuple(clases)
    return _TRANSITORIAS


def es_transitoria(exc: BaseException) -> bool:
    return isinstance(exc, transitorias())


def _reciclar_pool() -> None:
    """Tira el pool. Sin esto el reintento saca del pool la MISMA conexión muerta y falla igual."""
    try:
        from src.storage.connection import close_pool
        close_pool()
    except Exception:
        pass


def levantar_postgres(container: str = "energy_rag_pg", espera: float = 20.0) -> bool:
    """Intenta arrancar el container y espera a que ACEPTE una query, no a que docker responda.

    `docker start` vuelve enseguida; Postgres tarda unos segundos más en aceptar conexiones.
    Devolver antes de eso hace que el reintento falle por una razón distinta a la original.
    """
    try:
        subprocess.run(["docker", "start", container], capture_output=True, timeout=30)
    except Exception:
        return False
    _reciclar_pool()
    t0 = time.time()
    while time.time() - t0 < espera:
        try:
            from src.storage.connection import with_connection
            with with_connection() as c, c.cursor() as cur:
                cur.execute("SELECT 1")
            return True
        except Exception:
            _reciclar_pool()
            time.sleep(1.5)
    return False


def reintentar(fn: Callable[[], T], intentos: int = 3, espera: float = 2.0,
               levantar_db: bool = False, aviso: Callable[[str], None] | None = None) -> T:
    """Corre `fn`, reintentando SOLO ante fallas transitorias.

    `levantar_db=True` habilita el `docker start` — arrancar un servicio es un efecto lateral,
    así que lo decide quien llama (la interfaz sí, una librería no).
    """
    ultima: BaseException | None = None
    for i in range(intentos):
        try:
            return fn()
        except BaseException as exc:
            if not es_transitoria(exc):
                raise                       # bug: fallar rápido y fuerte
            ultima = exc
            if i == intentos - 1:
                break
            _reciclar_pool()
            if aviso:
                aviso(f"servicio caído ({type(exc).__name__}), reintento {i + 1}/{intentos - 1}…")
            if levantar_db:
                levantar_postgres()
            time.sleep(espera * (i + 1))    # backoff lineal: alcanza para un reinicio de container
    raise ultima  # type: ignore[misc]


def respuesta_vacia(r) -> bool:
    """Ollama agota sus reintentos devolviendo texto vacío, no excepción. Esto lo caza."""
    if r is None:
        return True
    txt = r.get("text", "") if isinstance(r, dict) else getattr(r, "text", "")
    return not str(txt).strip()
