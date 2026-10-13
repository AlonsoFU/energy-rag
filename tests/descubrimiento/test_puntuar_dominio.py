"""Tests de scripts/puntuar_dominio.py con datos inventados (sin red, sin BD)."""
import json

import pytest

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


def test_duplicado_en_etiquetado():
    with pytest.raises(ValueError, match="etiquetado.*'?7'?.*duplicado"):
        puntuar([_e("7", "en_dominio"), _e("7", "fuera_de_dominio")], [])


def test_duplicado_en_puntajes():
    with pytest.raises(ValueError, match="puntajes.*7.*duplicado"):
        puntuar([_e("7", "en_dominio")], [_p("7", "en_dominio"), _p("7", "dudosa")])


def test_valores_invalidos_cada_uno():
    with pytest.raises(ValueError, match="etiqueta invalida 'rara'"):
        puntuar([_e("1", "rara")], [])
    with pytest.raises(ValueError, match="clase invalida 'quizas'"):
        puntuar([_e("1", "en_dominio")], [_p("1", "quizas")])
    with pytest.raises(ValueError, match="particion invalida 'train'"):
        puntuar([_e("1", "en_dominio", "train")], [])


def test_varios_problemas_en_un_solo_mensaje():
    et = [_e("1", "rara"), _e("2", "en_dominio", "train"), _e("2", "en_dominio")]
    pu = [_p("1", "quizas"), _p("1", "dudosa")]
    with pytest.raises(ValueError) as exc:
        puntuar(et, pu)
    msg = str(exc.value)
    for esperado in ("etiqueta invalida 'rara'", "particion invalida 'train'",
                     "id_norma 2: duplicado", "clase invalida 'quizas'",
                     "id_norma 1: duplicado"):
        assert esperado in msg


def test_clave_obligatoria_ausente():
    e_sin_etiqueta = {"id_norma": "1", "particion": "dev"}
    with pytest.raises(ValueError, match="etiquetado.*falta la clave 'etiqueta'"):
        puntuar([e_sin_etiqueta], [])
    with pytest.raises(ValueError, match="puntajes.*falta la clave 'clase'"):
        puntuar([_e("1", "en_dominio")], [{"id_norma": "1", "puntaje": 0.5}])


def test_clase_no_nula_con_puntaje_null_se_puntua_por_clase():
    r = puntuar([_e("1", "en_dominio")], [_p("1", "en_dominio", None)])["particiones"]["dev"]
    assert r["clasificadas_en_dominio"] == 1
    assert r["sin_puntaje"] == 0
    assert r["precision"] == 1.0


def test_fuera_correcta_no_es_caida():
    r = puntuar([_e("1", "fuera_de_dominio")], [_p("1", "fuera_de_dominio")])["particiones"]["dev"]
    assert r["fuera_correctas"] == 1
    assert r["en_dominio_caidas_fuera"] == []


def test_reconciliacion_total_caso_mixto():
    et = [_e("1", "en_dominio"), _e("2", "fuera_de_dominio"),   # clasificadas en dominio
          _e("3", "en_dominio"), _e("4", "fuera_de_dominio"),   # dudosas
          _e("5", "en_dominio"), _e("6", "en_dominio"),         # sin puntaje (null, ausente)
          _e("7", "fuera_de_dominio"),                          # fuera correcta
          _e("8", "en_dominio")]                                # caida fuera
    pu = [_p("1", "en_dominio"), _p("2", "en_dominio"), _p("3", "dudosa"),
          _p("4", "dudosa"), _p("5", None, None), _p("7", "fuera_de_dominio"),
          _p("8", "fuera_de_dominio")]
    r = puntuar(et, pu)["particiones"]["dev"]
    assert (r["clasificadas_en_dominio"], r["dudosas"], r["sin_puntaje"],
            r["fuera_correctas"], len(r["en_dominio_caidas_fuera"])) == (2, 2, 2, 1, 1)
    assert r["total"] == 8 == (r["clasificadas_en_dominio"] + r["dudosas"] + r["sin_puntaje"]
                               + r["fuera_correctas"] + len(r["en_dominio_caidas_fuera"]))


def test_main_entrada_invalida_devuelve_2_sin_salida(tmp_path, capsys):
    et = tmp_path / "et.jsonl"
    pu = tmp_path / "pu.jsonl"
    sal = tmp_path / "sal.json"
    et.write_text(json.dumps(_e("1", "rara")) + "\n")
    pu.write_text("")
    assert main(["--etiquetado", str(et), "--puntajes", str(pu), "--salida", str(sal)]) == 2
    assert not sal.exists()
    assert "etiqueta invalida" in capsys.readouterr().err


def test_main_json_malformado_devuelve_2_con_numero_de_linea(tmp_path, capsys):
    et = tmp_path / "et.jsonl"
    pu = tmp_path / "pu.jsonl"
    sal = tmp_path / "sal.json"
    et.write_text(json.dumps(_e("1", "en_dominio")) + "\n{no es json\n")
    pu.write_text("")
    assert main(["--etiquetado", str(et), "--puntajes", str(pu), "--salida", str(sal)]) == 2
    assert not sal.exists()
    assert "linea 2" in capsys.readouterr().err


def test_main_particion_sin_clasificadas_precision_null(tmp_path):
    et = tmp_path / "et.jsonl"
    pu = tmp_path / "pu.jsonl"
    sal = tmp_path / "sal.json"
    et.write_text(json.dumps(_e("1", "en_dominio", "heldout")) + "\n")
    pu.write_text(json.dumps(_p("1", "fuera_de_dominio")) + "\n")
    assert main(["--etiquetado", str(et), "--puntajes", str(pu), "--salida", str(sal)]) == 0
    assert json.loads(sal.read_text())["particiones"]["heldout"]["precision"] is None


def test_ids_int_y_str_mezclados():
    r = puntuar([_e(1, "en_dominio"), _e("2", "en_dominio")],
                [_p("1", "en_dominio"), _p(2, "en_dominio")])["particiones"]["dev"]
    assert r["clasificadas_en_dominio"] == 2
    assert r["sin_puntaje"] == 0
    with pytest.raises(ValueError, match="duplicado"):
        puntuar([_e(1, "en_dominio"), _e("1", "en_dominio")], [])
