from src.pipelines import concept_injection as ci


def _index():
    return {
        "coordinador independiente del sistema electrico nacional":
            ("1160108", "2", "órgano técnico independiente…",
             "Coordinador independiente del sistema eléctrico nacional"),
        "cen": ("1160108", "2", "órgano técnico independiente…",
                "Coordinador independiente del sistema eléctrico nacional"),
    }


def _concepts():
    return [{"nombre": "Coordinador independiente del sistema eléctrico nacional",
             "aliases": ["CEN"]},
            {"nombre": "Panel de Expertos", "aliases": []}]


def test_subject_found_any_phrasing(monkeypatch):
    monkeypatch.setattr(ci, "_concept_index", _index)
    monkeypatch.setattr(ci, "_all_concepts", _concepts)
    for q in ["explícame qué es el Coordinador independiente del sistema eléctrico nacional",
              "a qué se refiere el Coordinador independiente del sistema eléctrico nacional",
              "Coordinador independiente del sistema eléctrico nacional"]:
        s = ci.find_subject_concept(q)
        assert s is not None and s[0] == "1160108" and s[1] == "2"


def test_alias_subject_sets_alias_token(monkeypatch):
    monkeypatch.setattr(ci, "_concept_index", _index)
    monkeypatch.setattr(ci, "_all_concepts", _concepts)
    s = ci.find_subject_concept("qué dice la norma sobre el CEN")
    assert s is not None and s[4] == "CEN"


def test_no_concept_returns_none(monkeypatch):
    monkeypatch.setattr(ci, "_concept_index", _index)
    monkeypatch.setattr(ci, "_all_concepts", _concepts)
    assert ci.find_subject_concept("cuál es la capital de Australia") is None


def test_two_distinct_concepts_returns_none(monkeypatch):
    monkeypatch.setattr(ci, "_concept_index", _index)
    monkeypatch.setattr(ci, "_all_concepts", _concepts)
    s = ci.find_subject_concept(
        "relación entre el Coordinador independiente del sistema eléctrico nacional y el Panel de Expertos")
    assert s is None


def test_overlapping_match_picks_longest(monkeypatch):
    idx = {"coordinador": ("999", "1", "x", "Coordinador"),
           "coordinador independiente del sistema electrico nacional":
               ("1160108", "2", "órgano técnico…",
                "Coordinador independiente del sistema eléctrico nacional")}
    monkeypatch.setattr(ci, "_concept_index", lambda: idx)
    monkeypatch.setattr(ci, "_all_concepts", lambda: [
        {"nombre": "Coordinador", "aliases": []},
        {"nombre": "Coordinador independiente del sistema eléctrico nacional", "aliases": ["CEN"]}])
    s = ci.find_subject_concept("qué es el Coordinador independiente del sistema eléctrico nacional")
    assert s is not None and s[0] == "1160108"


def test_inject_fires_on_nonopener_phrasing(monkeypatch):
    monkeypatch.setattr(ci, "_concept_index", _index)
    monkeypatch.setattr(ci, "_all_concepts", _concepts)
    out = ci.inject_definition(
        "explícame qué es el Coordinador independiente del sistema eléctrico nacional", [])
    assert out and out[0].get("_injected") is True
    assert out[0]["id_norma"] == "1160108" and out[0]["articulo_numero"] == "2"


def test_inject_alias_nonopener(monkeypatch):
    monkeypatch.setattr(ci, "_concept_index", _index)
    monkeypatch.setattr(ci, "_all_concepts", _concepts)
    out = ci.inject_definition("información sobre el CEN", [])
    assert out and out[0].get("_alias_link") is True


def test_inject_noop_when_no_subject(monkeypatch):
    monkeypatch.setattr(ci, "_concept_index", _index)
    monkeypatch.setattr(ci, "_all_concepts", _concepts)
    docs = [{"id_norma": "x", "articulo_numero": "1"}]
    assert ci.inject_definition("cuál es la capital de Australia", docs) == docs
