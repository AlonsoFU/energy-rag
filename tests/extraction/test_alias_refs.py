from src.core.catalogo import Catalogo, NormaEntry
from src.extraction.alias_refs import extract_alias_refs

CAT = Catalogo([
    NormaEntry(id_canonico="DFL_4", tipo="DFL", numero="4",
               aliases=["LGSE", "Ley General de Servicios Eléctricos"]),
    NormaEntry(id_canonico="DECRETO_62", tipo="DECRETO", numero="62",
               aliases=["Reglamento de Transferencias", "Reglamento de Transferencias de Potencia"]),
])


def test_lgse_alias_resolved():
    refs = extract_alias_refs("Conforme a la LGSE, las empresas eléctricas...", CAT)
    assert any(r.destino_norma_id == "DFL_4" for r in refs)


def test_full_alias_resolved():
    refs = extract_alias_refs("La Ley General de Servicios Eléctricos establece...", CAT)
    assert any(r.destino_norma_id == "DFL_4" for r in refs)


def test_no_match():
    refs = extract_alias_refs("Texto sin referencias.", CAT)
    assert refs == []
