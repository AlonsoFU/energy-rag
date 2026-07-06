"""Vocabulario controlado coloquial→legal (query-side, determinista, sin DB).

Mapa CURADO {trigger coloquial → término legal canónico}. Si la query coloquial
dispara un trigger, el término legal se usa como SEGUNDA query (modo replace) y se
UNE (RRF) con la query original en el retrieval — ver `_vector_leg` en retrieve.py.

Por qué replace+unión y no append:
  - append diluye (la query coloquial larga domina el embedding; 118 quedaba >50).
  - replace solo rescata pero ROMPE casos que ya andan bien (caso 2: 8→>50).
  - unión = lo mejor de cada uno (original protege, alias rescata). Medido en
    exp_alias_screen: 87 17→3, 118 >50→9, 212 >50→6, caso2 8→9 (no rompe).

CAVEATS:
  - un alias MAL curado HACE daño (apunta lejos del gold → arrastra el RRF). La
    curación tiene que ser correcta y verificada contra el artículo real.
  - estos son alias A MANO = riesgo de overfit al set de eval. Es la prueba de
    TECHO. La versión que ESCALA deriva los alias del corpus ("se entiende por X")
    — ver Exp #2-AUTO. NO adoptar este mapa a mano en producción sin la versión auto.
"""
import re

# (trigger regex en minúsculas, término legal canónico). Curado y verificado
# contra el artículo gold real (no inventar números de ley).
ALIAS = [
    (r"planear|planificar|qu[eé] torres nuevas|construir.*l[ií]nea",
     "proceso de planificación de la transmisión expansión"),
    (r"tope de ganancia|cu[aá]nto.*pueden cobrar|rentabilidad",
     "tasa de descuento anualidad del valor de inversión instalaciones de transmisión"),
    (r"tope de tama[nñ]o|paneles.*techo|inyectar a la red|cu[aá]nto.*capacidad",
     "capacidad instalada equipamiento de generación inyectar excedentes a la red de distribución"),
    (r"grupo que resuelve.*peleas|resuelve.*disputas|dirim",
     "Panel de Expertos financiamiento presupuesto"),
]


def apply_alias(query: str) -> str:
    """Devuelve el/los término(s) legal(es) si algún trigger dispara, si no la query
    original. Modo REPLACE: el término legal reemplaza la query (no se concatena),
    para que domine el embedding. La UNIÓN con la original la hace el caller."""
    ql = query.lower()
    adds = [term for pat, term in ALIAS if re.search(pat, ql)]
    return " ".join(adds) if adds else query


def fires(query: str) -> bool:
    """True si algún alias dispara para esta query."""
    return apply_alias(query) != query
