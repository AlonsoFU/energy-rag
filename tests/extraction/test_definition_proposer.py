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


def test_guard_rejects_fundamento_about_a_different_norm():
    # Picks the Decreto (numero 10) but justifies it talking about "Ley 20.936"
    # — the CNE hallucination. Guard A must reject it (→ needs_review later).
    llm = MockLLMProvider(canned_responses={
        "Concepto": '{"id_norma": "1146553", "articulo": "5", '
                    '"criterio": "jerarquia", '
                    '"fundamento": "La Ley 20.936 define la naturaleza..."}'})
    cands = [{"id_norma": "1146553", "articulo": "5", "numero": "10",
              "rank": 2, "fecha": "2019-02-01", "definicion": "reglamento..."}]
    r = propose_definition_source("CNE", cands, llm=llm)
    assert r["status"] == "no-proposal"
    assert r.get("reason") == "fundamento-mismatch"


def test_guard_accepts_fundamento_citing_the_picked_norm():
    llm = MockLLMProvider(canned_responses={
        "Concepto": '{"id_norma": "29819", "articulo": "23", '
                    '"criterio": "sustancia", '
                    '"fundamento": "La Ley 18.410 crea la SEC..."}'})
    cands = [{"id_norma": "29819", "articulo": "23", "numero": "18410",
              "rank": 3, "fecha": "1985-05-22", "definicion": "sucesora legal..."}]
    r = propose_definition_source("SEC", cands, llm=llm)
    assert r["id_norma"] == "29819" and r["confianza"] == "baja"
