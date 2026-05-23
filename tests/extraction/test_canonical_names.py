"""Pure unit tests for rule A (canonical name extraction) and decide_action.

DB-free by design: representative real-concept examples assert the rule's
behaviour. The full-corpus distribution (6 high / 1 low / 327 no-fire) is
validated separately by running scripts/dryrun_canonical_names.py against the
real DB (the test container is empty, so a distribution test there is moot).
"""
from src.extraction.canonical_names import (
    decide_action,
    extract_canonical,
    _na,
)


# --- extract_canonical -------------------------------------------------------

def test_no_fire_when_definition_does_not_restate_name():
    canonical, conf = extract_canonical(
        "Cliente", "Persona natural o jurídica que acredite dominio…")
    assert (canonical, conf) == (None, "no-fire")


def test_high_cut_at_period():
    canonical, conf = extract_canonical("Comisión", "Comisión Nacional de Energía.")
    assert conf == "high"
    assert canonical == "Comisión Nacional de Energía"


def test_high_cut_at_participle():
    canonical, conf = extract_canonical(
        "Panel", "Panel de Expertos establecido en el Título VI del decreto…")
    assert conf == "high"
    assert canonical == "Panel de Expertos"


def test_high_preserves_original_case_and_accents():
    canonical, conf = extract_canonical(
        "Coordinador",
        "Coordinador independiente del sistema eléctrico nacional, a quien…")
    assert conf == "high"
    assert canonical == "Coordinador independiente del sistema eléctrico nacional"


def test_low_when_too_long_cut_at_relative_clause():
    canonical, conf = extract_canonical(
        "Comité",
        "Comité de adjudicación y supervisión del o los estudios de "
        "valorización a que se refiere el inciso segundo del artículo 108° de la Ley")
    assert conf == "low"
    assert canonical == ("Comité de adjudicación y supervisión del o los "
                         "estudios de valorización")


def test_no_fire_when_name_not_extended():
    canonical, conf = extract_canonical("Comité", "Comité. Algo más.")
    assert (canonical, conf) == (None, "no-fire")


def test_low_when_no_boundary_found():
    canonical, conf = extract_canonical("Foo", "Foo bar baz qux quux corge")
    assert conf == "low"
    assert canonical is None


def test_empty_definition_is_no_fire():
    assert extract_canonical("X", "") == (None, "no-fire")


# --- decide_action -----------------------------------------------------------

def test_decide_skip_when_already_canonicalized():
    a = decide_action("Comisión", "Comisión Nacional de Energía.",
                      metadata={"canonical_source": "definition_opening"},
                      other_names=set())
    assert a["action"] == "skip"
    assert a["reason"] == "already_canonicalized"


def test_decide_skip_on_no_fire():
    a = decide_action("Cliente", "Persona natural o jurídica…",
                      metadata=None, other_names=set())
    assert a["action"] == "skip"
    assert a["reason"] == "no-fire"


def test_decide_rename_on_high_no_collision():
    a = decide_action("Comisión", "Comisión Nacional de Energía.",
                      metadata=None, other_names=set())
    assert a["action"] == "rename"
    assert a["canonical"] == "Comisión Nacional de Energía"


def test_decide_review_on_low():
    a = decide_action(
        "Comité",
        "Comité de adjudicación y supervisión del o los estudios de "
        "valorización a que se refiere el inciso segundo…",
        metadata=None, other_names=set())
    assert a["action"] == "review"
    assert a["reason"].startswith("low_confidence")
    assert a["canonical"].startswith("Comité de adjudicación")


def test_decide_review_on_collision():
    a = decide_action("Comisión", "Comisión Nacional de Energía.",
                      metadata=None,
                      other_names={_na("Comisión Nacional de Energía")})
    assert a["action"] == "review"
    assert a["reason"] == "collision"
