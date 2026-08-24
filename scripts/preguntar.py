"""FASE 1.2 — interfaz de uso. Lo mínimo para que alguien consulte sin escribir Python.

    preguntar.py "¿cada cuánto se calcula el balance de transferencias?"
    preguntar.py --obligaciones coordinador
    preguntar.py --plazos
    preguntar.py --cambios

No es una aplicación web: es la capa que faltaba entre el sistema y una persona.
Los errores se explican en castellano — antes cualquier fallo salía como stacktrace de Python.
"""
import argparse
import sys
import time


def _fatal(msg, detalle=""):
    print(f"\n  ⚠️  {msg}", file=sys.stderr)
    if detalle:
        print(f"      {detalle}", file=sys.stderr)
    sys.exit(1)


def _chequeos():
    """Verifica lo que suele fallar ANTES de cargar modelos (que tarda ~40 s)."""
    import logging
    import urllib.request
    # el pool de psycopg escribe su propio error de conexion en stderr y reintenta; sin
    # silenciarlo, el usuario ve dos volcados tecnicos antes de nuestro mensaje.
    logging.getLogger("psycopg.pool").setLevel(logging.CRITICAL)
    try:
        from src.components.vectorstore import with_connection
        with with_connection() as c, c.cursor() as cur:
            cur.execute("SELECT 1")
    except Exception as e:
        # el container se apaga solo (CLAUDE.md): intentar levantarlo antes de rendirse.
        from src.core.resiliencia import levantar_postgres
        print("  … la base no responde, levantándola…", flush=True)
        if not levantar_postgres():
            _fatal("La base de datos no responde y no se pudo levantar.",
                   f"Probá a mano:  docker start energy_rag_pg     ({type(e).__name__})")
    try:
        urllib.request.urlopen("http://localhost:11434/api/tags", timeout=5)
    except Exception:
        _fatal("El modelo de lenguaje no responde.",
               "Probá:  ollama serve      (o revisá que Ollama esté instalado)")


def responder(pregunta):
    _chequeos()
    from src.components.embedder import Qwen3Embedder
    from src.components.reranker import get_reranker
    from src.components.vectorstore import PostgresStore
    from src.components.llm import get_llm_provider
    from src.pipelines.retrieve import SimpleRetriever
    from src.pipelines.generate import generate_answer
    from src.core import config as cfg

    print("  buscando…", flush=True)
    t0 = time.time()
    llm = get_llm_provider()
    store = PostgresStore()
    cfg.settings.embed_4b_dense = True
    cfg.settings.embed_4b_dim = 1024
    cfg.settings.embed_4b_cpu = True
    retr = SimpleRetriever(store, Qwen3Embedder(), get_reranker(),
                           top_bm25=cfg.settings.retrieval_pool_depth,
                           top_vector=cfg.settings.retrieval_pool_depth, llm=llm)
    # FASE 1.3: los chequeos de arriba corren ANTES de cargar modelos (~40 s). Si Postgres se
    # cae DURANTE el retrieval, sin esto la consulta se pierde entera. `reintentar` distingue
    # caida de servicio (reintenta, y levanta el container) de bug (falla al toque).
    from src.core import resiliencia
    aviso = lambda m: print(f"  … {m}", flush=True)
    try:
        docs = resiliencia.reintentar(lambda: retr.retrieve(pregunta, top_k=10),
                                      levantar_db=True, aviso=aviso)
        r = resiliencia.reintentar(
            lambda: generate_answer(pregunta, docs, llm=llm, model="ollama/qwen3:30b-a3b"),
            levantar_db=True, aviso=aviso)
    except Exception as e:
        _fatal("No se pudo generar la respuesta.", f"{type(e).__name__}: {e}")
    # Ollama agota sus 3 reintentos internos devolviendo texto VACIO, no excepcion: no cae en
    # el `except` de arriba y el usuario veria una respuesta en blanco sin explicacion.
    if resiliencia.respuesta_vacia(r):
        _fatal("El modelo no devolvió respuesta (se quedó colgado o sin memoria).",
               "Probá de nuevo. Si se repite:  ollama ps   y revisá que no haya otro modelo cargado.")

    print(f"\n{r['text']}\n")
    print(f"  ── {time.time() - t0:.0f} s · {len(docs)} artículos consultados")
    if docs:
        print("  ── fuentes en el pool:")
        vistos = set()
        for d in docs[:6]:
            k = f"{d.get('id_norma')}/{d.get('articulo_numero')}"
            if k in vistos:
                continue
            vistos.add(k)
            print(f"       [{d.get('id_norma')} art {d.get('articulo_numero')}]")

    # FASE 3.1: las preguntas REALES son el unico insumo que no se fabrica desde adentro.
    from src.core import bitacora
    v, nota = bitacora.preguntar_veredicto()
    bitacora.registrar(pregunta, r["text"], docs, time.time() - t0, v, nota)


def obligaciones(sujeto):
    _chequeos()
    from scripts.mapa_obligaciones import por_sujeto, resumen
    por_sujeto(sujeto) if sujeto else resumen()


def plazos():
    _chequeos()
    from scripts.mapa_obligaciones import plazos as _p
    _p()


def cambios():
    _chequeos()
    from psycopg.rows import dict_row
    from src.components.vectorstore import with_connection
    with with_connection() as c, c.cursor(row_factory=dict_row) as cur:
        cur.execute("""SELECT e.id_norma, e.tipo_evento, e.detectado_en,
                              e.impacto->>'n_citas' AS citas, n.tipo, n.numero
                       FROM norma_evento e LEFT JOIN normas n ON n.id_norma = e.id_norma
                       ORDER BY e.detectado_en DESC LIMIT 30""")
        r = cur.fetchall()
    if not r:
        print("\n  Sin cambios registrados. El monitor todavía no corrió en producción.")
        print("  Para correrlo:  scripts/monitor_run.sh")
        return
    print(f"\n=== últimos cambios detectados ({len(r)}) ===")
    for x in r:
        nom = f"{x['tipo']} {x['numero']}" if x["tipo"] else x["id_norma"]
        cit = f" · la citan {x['citas']} artículos" if x["citas"] and x["citas"] != "0" else ""
        print(f"  {x['detectado_en']:%Y-%m-%d}  {x['tipo_evento']:20} {nom}{cit}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(
        description="Consultas sobre normativa eléctrica de la Subgerencia de Mercados.")
    ap.add_argument("pregunta", nargs="?", help="pregunta en lenguaje natural")
    ap.add_argument("--obligaciones", nargs="?", const="", metavar="SUJETO",
                    help="qué obliga la normativa a un sujeto (ej: coordinador)")
    ap.add_argument("--plazos", action="store_true", help="obligaciones con plazo")
    ap.add_argument("--cambios", action="store_true", help="cambios normativos detectados")
    ap.add_argument("--bitacora", action="store_true",
                    help="preguntas reales registradas y su veredicto")
    a = ap.parse_args()
    if a.bitacora:
        from src.core.bitacora import resumen
        resumen()
    elif a.plazos:
        plazos()
    elif a.cambios:
        cambios()
    elif a.obligaciones is not None:
        obligaciones(a.obligaciones)
    elif a.pregunta:
        responder(a.pregunta)
    else:
        ap.print_help()
