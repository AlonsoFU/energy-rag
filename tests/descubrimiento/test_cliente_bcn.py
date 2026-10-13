import pytest

import email.message
import http.client
import io
import urllib.error
import urllib.request
import urllib.response

from src.descubrimiento import cliente_bcn
from src.descubrimiento.cliente_bcn import (
    USER_AGENT,
    construir_opener,
    ClienteBCN,
    CuotaAgotada,
    ErrorBCN,
    HostNoPermitido,
)

URL = "https://www.bcn.cl/leychile/navegar?idNorma=1"


class Falso:
    """Transporte, reloj y dormir simulados."""

    def __init__(self, statuses=None):
        self.t = 1000.0
        self.statuses = list(statuses or [])
        self.urls = []
        self.dormidos = []

    def transporte(self, url, headers):
        self.urls.append(url)
        assert "User-Agent" in headers
        return (self.statuses.pop(0) if self.statuses else 200), b"ok"

    def reloj(self):
        return self.t

    def dormir(self, s):
        self.dormidos.append(s)
        self.t += s

    def cliente(self, intervalo=20.0):
        return ClienteBCN(intervalo, self.transporte, self.reloj, self.dormir)


def test_segunda_peticion_duerme_lo_que_falta():
    f = Falso()
    c = f.cliente()
    c.obtener(URL)
    f.t += 5
    c.obtener(URL)
    assert f.dormidos == [15.0]
    assert c.peticiones == 2


def test_si_ya_paso_el_intervalo_no_duerme():
    f = Falso()
    c = f.cliente()
    c.obtener(URL)
    f.t += 25
    c.obtener(URL)
    assert f.dormidos == []


@pytest.mark.parametrize(
    "url",
    [
        "https://example.com/x",
        "https://bcn.cl.evil.com/x",
        "https://evilbcn.cl/x",
        "https://bcn.cl@evil.com/x",
    ],
)
def test_host_ajeno_se_rechaza_sin_llamar_transporte(url):
    f = Falso()
    c = f.cliente()
    with pytest.raises(HostNoPermitido):
        c.obtener(url)
    assert f.urls == []
    assert c.peticiones == 0


@pytest.mark.parametrize(
    "host",
    ["bcn.cl", "www.bcn.cl", "leychile.cl", "www.leychile.cl", "localhost", "127.0.0.1"],
)
def test_hosts_permitidos_pasan(host):
    f = Falso()
    c = f.cliente()
    assert c.obtener(f"https://{host}/x") == b"ok"
    assert len(f.urls) == 1


def test_429_corta_y_las_siguientes_no_llaman_transporte():
    f = Falso([429])
    c = f.cliente()
    with pytest.raises(CuotaAgotada):
        c.obtener(URL)
    assert c.peticiones == 1
    with pytest.raises(CuotaAgotada):
        c.obtener(URL)
    assert c.peticiones == 1
    assert len(f.urls) == 1


def test_500_lanza_errorbcn_y_sigue_utilizable():
    f = Falso([500, 200])
    c = f.cliente()
    with pytest.raises(ErrorBCN) as e:
        c.obtener(URL)
    assert not isinstance(e.value, (CuotaAgotada, HostNoPermitido))
    assert "500" in str(e.value) and URL in str(e.value)
    assert c.obtener(URL) == b"ok"
    assert c.peticiones == 2


def test_excepciones_heredan_de_errorbcn():
    assert issubclass(CuotaAgotada, ErrorBCN)
    assert issubclass(HostNoPermitido, ErrorBCN)


@pytest.mark.parametrize(
    "url", ["file://localhost/etc/hostname", "ftp://bcn.cl/x", "//bcn.cl/x"]
)
def test_esquema_no_http_se_rechaza(url):
    f = Falso()
    c = f.cliente()
    with pytest.raises(HostNoPermitido):
        c.obtener(url)
    assert f.urls == [] and c.peticiones == 0


def test_host_en_mayusculas_pasa():
    f = Falso()
    assert f.cliente().obtener("https://BCN.CL/x") == b"ok"


@pytest.mark.parametrize(
    "url", ["https://bcn.cl./x", "https://user@www.bcn.cl/x", "https://user:p@bcn.cl/x"]
)
def test_punto_final_y_userinfo_se_rechazan(url):
    f = Falso()
    with pytest.raises(HostNoPermitido):
        f.cliente().obtener(url)
    assert f.urls == []


def test_puerto_se_acepta_si_el_host_es_permitido():
    f = Falso()
    assert f.cliente().obtener("http://bcn.cl:8080/x") == b"ok"


def test_handler_de_redireccion_no_sigue_302():
    opener = construir_opener()
    manejadores = [
        h for h in opener.handlers if isinstance(h, urllib.request.HTTPRedirectHandler)
    ]
    assert len(manejadores) == 1
    req = urllib.request.Request(URL)
    assert (
        manejadores[0].redirect_request(req, None, 302, "Found", {}, "https://evil.com/")
        is None
    )


def test_tercera_peticion_mide_intervalo_entre_inicios():
    f = Falso()
    c = f.cliente()
    c.obtener(URL)          # t=1000
    f.t += 5
    c.obtener(URL)          # duerme 15 -> inicio en 1020
    f.t += 8
    c.obtener(URL)          # faltan 12
    assert f.dormidos == [15.0, 12.0]


def test_excepcion_de_transporte_cuenta_sale_como_errorbcn_y_sigue_usable():
    f = Falso()
    llamadas = []

    def transporte(url, headers):
        llamadas.append(url)
        if len(llamadas) == 1:
            raise TimeoutError("lento")
        return 200, b"ok"

    c = ClienteBCN(20.0, transporte, f.reloj, f.dormir)
    with pytest.raises(ErrorBCN) as e:
        c.obtener(URL)
    assert isinstance(e.value.__cause__, TimeoutError)
    assert not isinstance(e.value, CuotaAgotada)
    assert c.peticiones == 1
    assert c.obtener(URL) == b"ok"
    assert c.peticiones == 2


def test_tras_429_la_siguiente_no_duerme():
    f = Falso([429])
    c = f.cliente()
    with pytest.raises(CuotaAgotada):
        c.obtener(URL)
    with pytest.raises(CuotaAgotada):
        c.obtener(URL)
    assert f.dormidos == []


def test_user_agent_de_navegador():
    visto = {}

    def transporte(url, headers):
        visto.update(headers)
        return 200, b""

    ClienteBCN(transporte=transporte).obtener(URL)
    assert visto["User-Agent"] == USER_AGENT
    assert visto["User-Agent"].startswith("Mozilla/5.0 ")
    assert "Chrome/" in visto["User-Agent"]


@pytest.mark.parametrize(
    "excepcion",
    [http.client.BadStatusLine("basura"), http.client.IncompleteRead(b"par")],
)
def test_httpexception_sale_como_errorbcn(excepcion):
    f = Falso()
    llamadas = []

    def transporte(url, headers):
        llamadas.append(url)
        if len(llamadas) == 1:
            raise excepcion
        return 200, b"ok"

    c = ClienteBCN(20.0, transporte, f.reloj, f.dormir)
    with pytest.raises(ErrorBCN) as e:
        c.obtener(URL)
    assert e.value.__cause__ is excepcion
    assert not isinstance(e.value, CuotaAgotada)
    assert c.obtener(URL) == b"ok"


@pytest.mark.parametrize(
    "url",
    [" http://bcn.cl/a", "\thttp://bcn.cl/", "http://bcn.cl\t/", "http://bcn.cl/a\n",
     "http://bcn.cl/a\x7f", None, b"http://bcn.cl/"],
)
def test_url_con_blancos_o_control_se_rechaza(url):
    f = Falso()
    c = f.cliente()
    with pytest.raises(HostNoPermitido):
        c.obtener(url)
    assert f.urls == [] and c.peticiones == 0


@pytest.mark.parametrize(
    "url", ["http://bcn.cl:99999/", "http://bcn.cl:abc/", "http://bcn.cl:0/"]
)
def test_puerto_invalido_se_rechaza(url):
    f = Falso()
    with pytest.raises(HostNoPermitido):
        f.cliente().obtener(url)
    assert f.urls == []


def test_puerto_valido_pasa():
    assert Falso().cliente().obtener("http://bcn.cl:8080/x") == b"ok"


def test_transporte_por_defecto_ante_302_no_sigue_la_redireccion(monkeypatch):
    vistas = []

    class HTTPFalso(urllib.request.HTTPHandler):
        def http_open(self, req):
            vistas.append(req.full_url)
            cab = email.message.Message()
            cab["Location"] = "http://evil.com/robo"
            resp = urllib.response.addinfourl(
                io.BytesIO(b"redir"), cab, req.full_url, code=302
            )
            resp.msg = "Found"
            return resp

    monkeypatch.setattr(
        cliente_bcn, "construir_opener", lambda: construir_opener(HTTPFalso())
    )
    origen = "http://www.bcn.cl/x"
    status, cuerpo = cliente_bcn._transporte_urllib(origen, {"User-Agent": "t"})
    assert status == 302
    assert vistas == [origen]

    vistas.clear()
    c = ClienteBCN(transporte=cliente_bcn._transporte_urllib)
    with pytest.raises(ErrorBCN) as e:
        c.obtener(origen)
    assert "302" in str(e.value)
    assert vistas == [origen]
