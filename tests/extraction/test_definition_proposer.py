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


def test_guard_flags_fundamento_about_a_different_norm():
    # Picks Decreto 10 (title says "DECRETO 10…") but justifies it talking about
    # "Ley 20.936" — the CNE hallucination. Guard A flags it (keeps the pick,
    # since it's needs_review; the human reviews the warning).
    llm = MockLLMProvider(canned_responses={
        "Concepto": '{"id_norma": "1146553", "articulo": "5", '
                    '"criterio": "jerarquia", '
                    '"fundamento": "La Ley 20.936 define la naturaleza..."}'})
    cands = [{"id_norma": "1146553", "articulo": "5", "numero": "10",
              "titulo": "DECRETO 10 APRUEBA REGLAMENTO DE VALORIZACIÓN",
              "rank": 2, "fecha": "2019-02-01", "texto": "reglamento..."}]
    r = propose_definition_source("CNE", cands, llm=llm)
    assert r["status"] == "proposed"
    assert r["fundamento_warning"] is True


def test_guard_ok_when_fundamento_cites_title_number_despite_bad_numero():
    # DL 2224 is mislabeled numero=20776; the title carries the real "2224".
    # A fundamento citing "DL 2224" must NOT be flagged.
    llm = MockLLMProvider(canned_responses={
        "Concepto": '{"id_norma": "6857", "articulo": "6º", '
                    '"criterio": "sustancia", '
                    '"fundamento": "El DL 2.224 crea la Comisión..."}'})
    cands = [{"id_norma": "6857", "articulo": "6º", "numero": "20776",
              "titulo": "DECRETO LEY 2224 CREA EL MINISTERIO Y LA CNE",
              "rank": 3, "fecha": "1978-06-08", "texto": "será persona jurídica..."}]
    r = propose_definition_source("CNE", cands, llm=llm)
    assert r["id_norma"] == "6857" and r["fundamento_warning"] is False
