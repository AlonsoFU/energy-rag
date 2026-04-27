from datetime import date

from src.pipelines.date_extraction import (
    extract_fecha_publicacion,
    parse_date,
)


# --- parse_date --------------------------------------------------------------

def test_parse_iso_date():
    assert parse_date("2020-03-15") == date(2020, 3, 15)


def test_parse_numeric_dot_date():
    assert parse_date("15.03.2020") == date(2020, 3, 15)


def test_parse_numeric_dash_date():
    assert parse_date("15-03-2020") == date(2020, 3, 15)


def test_parse_numeric_slash_date():
    assert parse_date("15/03/2020") == date(2020, 3, 15)


def test_parse_two_digit_year_recent():
    # 24 -> 2024
    assert parse_date("15.03.24") == date(2024, 3, 15)


def test_parse_two_digit_year_old():
    # 80 -> 1980
    assert parse_date("15.03.80") == date(1980, 3, 15)


def test_parse_spanish_date():
    assert parse_date("15 de marzo de 2020") == date(2020, 3, 15)


def test_parse_spanish_date_setiembre_alias():
    assert parse_date("3 de setiembre de 2010") == date(2010, 9, 3)


def test_parse_invalid_returns_none():
    assert parse_date("not a date") is None
    assert parse_date("99-99-9999") is None
    assert parse_date("") is None


# --- extract_fecha_publicacion: each layer ----------------------------------

def test_extract_from_existing_field_iso():
    assert extract_fecha_publicacion({"fecha_publicacion": "2020-03-15"}) == date(2020, 3, 15)


def test_extract_existing_field_takes_priority_over_texto():
    data = {
        "fecha_publicacion": "2020-03-15",
        "texto_completo": "Publicación: 01-ENE-2099",
    }
    assert extract_fecha_publicacion(data) == date(2020, 3, 15)


def test_extract_skips_empty_string_field():
    data = {
        "fecha_publicacion": "",
        "texto_completo": "Publicación: 13-JUN-2006\n\nArtículo 1...",
    }
    assert extract_fecha_publicacion(data) == date(2006, 6, 13)


def test_extract_from_pub_header_in_texto():
    data = {
        "texto_completo": "DECRETO 62.\n\nPublicación: 13-JUN-2006\n\nArtículo 1...",
    }
    assert extract_fecha_publicacion(data) == date(2006, 6, 13)


def test_extract_from_pub_header_with_lowercase_meses():
    # Header uses uppercase abbreviations in BCN, but be lenient on case.
    data = {"texto_completo": "Publicación: 13-jun-2006"}
    assert extract_fecha_publicacion(data) == date(2006, 6, 13)


def test_extract_from_texto_original_version():
    data = {
        "fecha_publicacion": "",
        "texto_completo": "",
        "versiones": [
            {"id_version": "2020-05-01", "descripcion": "Última Versión"},
            {"id_version": "2010-03-15", "descripcion": "Texto Original"},
        ],
    }
    assert extract_fecha_publicacion(data) == date(2010, 3, 15)


def test_extract_from_oldest_version_when_no_texto_original():
    data = {
        "fecha_publicacion": "",
        "texto_completo": "",
        "versiones": [
            {"id_version": "2020-05-01", "descripcion": "Última Versión"},
            {"id_version": "2014-09-04", "descripcion": "Intermedio"},
            {"id_version": "2007-08-24", "descripcion": ""},
        ],
    }
    assert extract_fecha_publicacion(data) == date(2007, 8, 24)


def test_extract_pub_header_beats_texto_original():
    # The "Publicación:" header in the rendered BCN view is the most reliable
    # source — it should win over a "Texto Original" version date.
    data = {
        "texto_completo": "Publicación: 31-DIC-2012\nbody...",
        "versiones": [
            {"id_version": "2010-01-01", "descripcion": "Texto Original"},
        ],
    }
    assert extract_fecha_publicacion(data) == date(2012, 12, 31)


def test_extract_from_santiago_signing_date_fallback():
    data = {
        "fecha_publicacion": "",
        "texto_completo": (
            "APRUEBA REGLAMENTO\n\n"
            "Núm. 10.- Santiago, 1 de febrero de 2019.\n\nVistos:..."
        ),
        "versiones": [],
    }
    assert extract_fecha_publicacion(data) == date(2019, 2, 1)


def test_extract_from_other_city_signing_date():
    data = {
        "texto_completo": (
            "RECTIFICA RESOLUCIÓN\n\n"
            "Núm. 70 exenta.- Iquique, 31 de enero de 2024.\n"
        ),
    }
    assert extract_fecha_publicacion(data) == date(2024, 1, 31)


def test_extract_returns_none_when_nothing_found():
    data = {"texto_completo": "Texto sin fecha alguna que indique publicación."}
    assert extract_fecha_publicacion(data) is None


def test_extract_handles_missing_fields_gracefully():
    assert extract_fecha_publicacion({}) is None


def test_extract_rejects_implausible_version_dates():
    # Real-world quirk: ley_21499.json has all versions stamped 2222-02-02.
    # Garbage like that must be rejected so we fall through to other layers
    # (here: the city signing date) rather than emitting a year-2222 date.
    data = {
        "fecha_publicacion": "",
        "texto_completo": "Núm. 21499.- Santiago, 25 de mayo de 2022.\n",
        "versiones": [
            {"id_version": "2222-02-02", "descripcion": ""},
            {"id_version": "2222-02-02", "descripcion": ""},
        ],
    }
    assert extract_fecha_publicacion(data) == date(2022, 5, 25)


def test_extract_ignores_non_dict_versions():
    # Defensive: if versiones contains non-dict entries, skip them rather
    # than crashing.
    data = {
        "versiones": ["bogus", None, {"id_version": "2010-03-15", "descripcion": "Texto Original"}],
    }
    assert extract_fecha_publicacion(data) == date(2010, 3, 15)
