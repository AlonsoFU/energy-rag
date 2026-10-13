import pytest

from src.descubrimiento.cliente_bcn import (
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
