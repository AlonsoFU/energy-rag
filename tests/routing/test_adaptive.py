from src.routing.adaptive import AdaptiveRouter


def test_router_classifies_simple_lookup():
    r = AdaptiveRouter()
    r.train_default()
    branch = r.classify("¿qué es COMA?")
    assert branch == "simple"


def test_router_classifies_complex_multi_norma():
    r = AdaptiveRouter()
    r.train_default()
    branch = r.classify("compara cómo el D.S. 62 y el DFL 4 regulan la potencia firme considerando enmiendas")
    assert branch == "complejo"


def test_router_default_when_unknown():
    r = AdaptiveRouter()
    r.train_default()
    branch = r.classify("hola")
    assert branch in ("simple", "complejo")
