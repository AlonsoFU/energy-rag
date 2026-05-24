from src.extraction.definition_quality import (
    is_label, is_remission, suspect_definition,
)


def test_circular_label_is_suspect():
    # Definition only restates the concept name → label.
    sus, reasons = suspect_definition(
        "Superintendencia de Electricidad y Combustibles",
        "la Superintendencia de Electricidad y Combustibles.")
    assert sus is True and "label" in reasons


def test_remission_is_suspect():
    sus, reasons = suspect_definition(
        "Coordinador", "el Coordinador a que se refiere el artículo 212 de la ley.")
    assert sus is True and "remission" in reasons


def test_substantive_definition_not_suspect():
    sus, reasons = suspect_definition(
        "Comisión Nacional de Energía",
        "persona jurídica de derecho público, funcionalmente descentralizada, "
        "con patrimonio propio y plena capacidad para adquirir y ejercer derechos.")
    assert sus is False and reasons == []


def test_is_label_true_when_only_name_words():
    assert is_label("Panel de Expertos", "el Panel de Expertos") is True


def test_is_label_false_when_adds_content():
    assert is_label("Panel de Expertos",
                    "órgano que resuelve discrepancias entre empresas eléctricas") is False


def test_is_remission_detects_cross_reference():
    assert is_remission("lo señalado en el artículo 5 del presente reglamento") is True
    assert is_remission("órgano técnico autónomo") is False


def test_empty_definition_is_suspect():
    sus, reasons = suspect_definition("X", "")
    assert sus is True and "empty" in reasons
