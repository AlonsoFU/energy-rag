"""Tests de scripts/puntuar_dominio.py con datos inventados (sin red, sin BD)."""
import json

from scripts.puntuar_dominio import main, puntuar


def _e(i, etiqueta, particion="dev"):
    return {"id_norma": i, "tipo": "LEY", "numero": i, "titulo": "t",
            "etiqueta": etiqueta, "motivo": "m", "particion": particion}


def _p(i, clase, puntaje=0.5):
    return {"id_norma": i, "puntaje": puntaje, "clase": clase}


def test_caso_base_precision():
    et = [_e(str(i), "en_dominio") for i in range(4)] + [_e("9", "fuera_de_dominio")]
    pu = [_p(str(i), "en_dominio") for i in range(4)] + [_p("9", "en_dominio")]
    r = puntuar(et, pu)["particiones"]["dev"]
    assert r["clasificadas_en_dominio"] == 5
    assert r["en_dominio_correctas"] == 4
    assert r["precision"] == 0.8


def test_dudosas_no_cambian_precision():
    et = [_e("1", "en_dominio"), _e("2", "en_dominio"), _e("3", "fuera_de_dominio")]
    pu = [_p("1", "en_dominio"), _p("2", "dudosa"), _p("3", "dudosa")]
    r = puntuar(et, pu)["particiones"]["dev"]
    assert r["precision"] == 1.0
    assert r["dudosas"] == 2


def test_en_dominio_caida_fuera():
    et = [_e("1", "en_dominio"), _e("2", "en_dominio")]
    pu = [_p("1", "fuera_de_dominio"), _p("2", "en_dominio")]
    r = puntuar(et, pu)["particiones"]["dev"]
    assert r["en_dominio_caidas_fuera"] == ["1"]


def test_sin_puntaje_ausente_y_nulo():
    et = [_e("1", "en_dominio"), _e("2", "en_dominio"), _e("3", "en_dominio")]
    pu = [_p("1", None, None), _p("3", "en_dominio")]
    r = puntuar(et, pu)["particiones"]["dev"]
    assert r["sin_puntaje"] == 2
    assert r["clasificadas_en_dominio"] == 1
    assert r["total"] == 3


def test_ninguna_en_dominio_precision_none():
    et = [_e("1", "en_dominio"), _e("2", "fuera_de_dominio")]
    pu = [_p("1", "fuera_de_dominio"), _p("2", "fuera_de_dominio")]
    assert puntuar(et, pu)["particiones"]["dev"]["precision"] is None


def test_no_etiquetadas_se_ignoran():
    res = puntuar([_e("1", "en_dominio")], [_p("1", "en_dominio"), _p("77", "en_dominio")])
    assert res["no_etiquetadas"] == 1
    assert res["particiones"]["dev"]["clasificadas_en_dominio"] == 1


def test_dev_y_heldout_separados():
    et = [_e("1", "en_dominio", "dev"), _e("2", "fuera_de_dominio", "heldout")]
    pu = [_p("1", "en_dominio"), _p("2", "en_dominio")]
    p = puntuar(et, pu)["particiones"]
    assert p["dev"]["precision"] == 1.0
    assert p["heldout"]["precision"] == 0.0
    assert p["dev"]["total"] == 1 and p["heldout"]["total"] == 1


def test_main_escribe_json_con_detalle(tmp_path, capsys):
    et = tmp_path / "et.jsonl"
    pu = tmp_path / "pu.jsonl"
    sal = tmp_path / "sal.json"
    et.write_text("\n".join(json.dumps(_e(i, "en_dominio")) for i in ("1", "2")) + "\n")
    pu.write_text(json.dumps(_p("1", "en_dominio", 0.9)) + "\n")
    assert main(["--etiquetado", str(et), "--puntajes", str(pu), "--salida", str(sal)]) == 0
    datos = json.loads(sal.read_text())
    assert datos["particiones"]["dev"]["sin_puntaje"] == 1
    det = {d["id_norma"]: d for d in datos["detalle"]}
    assert det["1"] == {"id_norma": "1", "particion": "dev", "etiqueta": "en_dominio",
                        "puntaje": 0.9, "clase": "en_dominio"}
    assert det["2"]["clase"] is None
    assert "dev" in capsys.readouterr().out
