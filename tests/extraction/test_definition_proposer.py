from src.components.llm import MockLLMProvider
from src.extraction.definition_proposer import propose_definition_source


def test_proposer_returns_low_confidence_pick():
    # MockLLMProvider matches canned_responses by SUBSTRING of the prompt;
    # "Concepto" appears in every proposer prompt → use it as the key.
    llm = MockLLMProvider(canned_responses={
        "Concepto": '{"id_norma": "B", "articulo": "23", '
                    '"criterio": "especialidad", '
                    '"fundamento": "ley orgánica del organismo"}'
    })
    cands = [
        {"id_norma": "A", "articulo": "2", "rank": 3, "fecha": None,
         "definicion": "la SEC."},
        {"id_norma": "B", "articulo": "23", "rank": 3, "fecha": "1985-05-22",
         "definicion": "entidad que sucedió legalmente al Servicio…"},
    ]
    r = propose_definition_source("SEC", cands, llm=llm)
    assert r["id_norma"] == "B" and r["articulo"] == "23"
    assert r["confianza"] == "baja"
    assert r["criterio"] == "especialidad"
    assert r["fundamento"]


def test_proposer_failopen_on_bad_json():
    llm = MockLLMProvider(canned_responses={"Concepto": "no soy json"})
    r = propose_definition_source("SEC", [
        {"id_norma": "A", "articulo": "2", "rank": 3, "fecha": None,
         "definicion": "la SEC."}], llm=llm)
    assert r["status"] == "no-proposal"


def test_proposer_rejects_pick_outside_candidates():
    llm = MockLLMProvider(canned_responses={
        "Concepto": '{"id_norma": "Z", "articulo": "9", "criterio": "x", '
                    '"fundamento": "y"}'})
    r = propose_definition_source("SEC", [
        {"id_norma": "A", "articulo": "2", "rank": 3, "fecha": None,
         "definicion": "la SEC."}], llm=llm)
    assert r["status"] == "no-proposal"
