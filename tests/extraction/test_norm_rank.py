from src.extraction.norm_rank import derive_rank, LEGAL, DECRETO, RESOLUCION


def test_dfl_is_legal_rank():
    assert derive_rank("DFL", "DFL 4 FIJA TEXTO REFUNDIDO…")[0] == LEGAL


def test_decreto_ley_is_legal_even_if_tipo_says_ley():
    rank, flagged = derive_rank("Ley", "DECRETO LEY 2224 CREA EL MINISTERIO")
    assert rank == LEGAL


def test_ley_is_legal():
    assert derive_rank("LEY", "LEY 18410 CREA LA SUPERINTENDENCIA")[0] == LEGAL


def test_decreto_is_regulatory():
    assert derive_rank("DECRETO", "DECRETO 37 APRUEBA REGLAMENTO")[0] == DECRETO


def test_resolucion_is_lowest():
    assert derive_rank("RESOLUCIÓN", "RESOLUCIÓN 711 EXENTA ESTABLECE")[0] == RESOLUCION


def test_mislabel_resolucion_tagged_ley_is_flagged():
    rank, flagged = derive_rank("LEY", "RESOLUCION 32 EXENTA NOMBRA REPRESENTANTE")
    assert rank == RESOLUCION and flagged is True


def test_clean_label_not_flagged():
    assert derive_rank("LEY", "LEY 20365 ESTABLECE…")[1] is False
