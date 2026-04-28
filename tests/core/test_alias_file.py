"""Validate the existing config/alias_normas.json structure.

The file uses a NESTED structure with curated sections, NOT the flat
TIPO_NUMERO -> [aliases] shape originally assumed in the plan.

Actual top-level keys:
  - "_comentario": str — human-readable note about the file
  - "confirmados": dict[str, str] — alias_phrase -> canonical name (lower-cased)
    e.g. "lgse" -> "ley general de servicios eléctricos"
  - "_comentario_conceptos": str — note about the conceptos_base section
  - "conceptos_base": dict[str, dict] — BCN LeyChile id (numeric string) ->
        { "_norma": str, "_nota": str (optional), "conceptos": list[str] }
    e.g. "1146553" -> {"_norma": "DFL 4/2006", "conceptos": [...]}
  - "por_confirmar": list — pending entries awaiting curation

Phase 4 reference-extraction loader will need an adapter that translates
this BCN-id-keyed nested structure into the canonical TIPO_NUMERO shape
expected by the alias matcher (e.g. parse "_norma" string -> ("DFL", "4")).
"""
import json
from pathlib import Path

ALIAS_FILE = Path(__file__).resolve().parents[2] / "config" / "alias_normas.json"


def _load():
    with open(ALIAS_FILE, encoding="utf-8") as f:
        return json.load(f)


def test_alias_file_exists_and_is_valid_json():
    assert ALIAS_FILE.exists(), f"{ALIAS_FILE} missing"
    data = _load()
    assert isinstance(data, dict)


def test_alias_file_has_known_top_level_sections():
    """The file must have the curated sections we rely on."""
    data = _load()
    expected_sections = {"confirmados", "conceptos_base", "por_confirmar"}
    found = expected_sections & set(data.keys())
    assert found == expected_sections, (
        f"expected all of {expected_sections}, got {set(data.keys())}"
    )


def test_alias_file_values_have_expected_types():
    """Each top-level non-comment value must have the right container type."""
    data = _load()
    assert isinstance(data["confirmados"], dict), "'confirmados' must be a dict"
    assert isinstance(data["conceptos_base"], dict), "'conceptos_base' must be a dict"
    assert isinstance(data["por_confirmar"], list), "'por_confirmar' must be a list"


def test_confirmados_maps_strings_to_strings():
    """'confirmados' is alias_phrase -> canonical_name, both strings."""
    data = _load()
    confirmados = data["confirmados"]
    assert len(confirmados) > 0, "'confirmados' should not be empty"
    for alias, canonical in confirmados.items():
        assert isinstance(alias, str) and alias.strip(), f"bad alias key: {alias!r}"
        assert isinstance(canonical, str) and canonical.strip(), (
            f"bad canonical for {alias!r}: {canonical!r}"
        )


def test_conceptos_base_entries_have_required_fields():
    """Each BCN-id-keyed entry must carry '_norma' and 'conceptos' (list)."""
    data = _load()
    conceptos_base = data["conceptos_base"]
    assert len(conceptos_base) > 0, "'conceptos_base' should not be empty"
    for bcn_id, entry in conceptos_base.items():
        # BCN LeyChile ids are numeric strings (e.g. "1146553")
        assert isinstance(bcn_id, str), f"bcn id {bcn_id!r} not a string"
        assert bcn_id.isdigit(), f"bcn id {bcn_id!r} should be numeric"
        assert isinstance(entry, dict), f"entry for {bcn_id} must be a dict"
        assert "_norma" in entry, f"entry {bcn_id} missing '_norma'"
        assert isinstance(entry["_norma"], str) and entry["_norma"].strip(), (
            f"entry {bcn_id} has bad '_norma'"
        )
        assert "conceptos" in entry, f"entry {bcn_id} missing 'conceptos'"
        assert isinstance(entry["conceptos"], list), (
            f"entry {bcn_id} 'conceptos' must be a list"
        )
        for c in entry["conceptos"]:
            assert isinstance(c, str) and c.strip(), (
                f"entry {bcn_id} has empty/non-string concepto"
            )
