"""Cliente BCN: único punto de salida a red de la historia cambios_dia.

Respeta un intervalo mínimo entre peticiones, corta ordenadamente ante un 429
y rechaza hosts fuera de la lista permitida.
"""
import time
import urllib.error
import urllib.request
from urllib.parse import urlsplit

HOSTS_PERMITIDOS = frozenset(
    {"bcn.cl", "www.bcn.cl", "leychile.cl", "www.leychile.cl", "localhost", "127.0.0.1"}
)

USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)


class ErrorBCN(Exception):
    """Base de los errores del cliente."""


class HostNoPermitido(ErrorBCN):
    """La URL apunta a un host fuera de la lista permitida."""


class CuotaAgotada(ErrorBCN):
    """BCN respondió 429; la instancia ya no hace más peticiones."""


def _transporte_urllib(url, headers):
    """Transporte por defecto: devuelve (status, cuerpo) también en errores HTTP."""
    peticion = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(peticion, timeout=60) as respuesta:
            return respuesta.status, respuesta.read()
    except urllib.error.HTTPError as e:
        return e.code, e.read()


class ClienteBCN:
    def __init__(self, intervalo=20.0, transporte=None, reloj=None, dormir=None):
        self.intervalo = intervalo
        self._transporte = transporte or _transporte_urllib
        self._reloj = reloj or time.monotonic
        self._dormir = dormir or time.sleep
        self._ultimo_inicio = None
        self._peticiones = 0
        self._cuota_agotada = False

    @property
    def peticiones(self):
        return self._peticiones

    def _validar_host(self, url):
        try:
            host = urlsplit(url).hostname
        except ValueError:
            host = None
        if host not in HOSTS_PERMITIDOS:
            raise HostNoPermitido(f"host no permitido: {host!r} en {url}")

    def obtener(self, url):
        self._validar_host(url)
        if self._cuota_agotada:
            raise CuotaAgotada(f"cuota agotada (429 previo); no se pide {url}")

        if self._ultimo_inicio is not None:
            falta = self.intervalo - (self._reloj() - self._ultimo_inicio)
            if falta > 0:
                self._dormir(falta)
        self._ultimo_inicio = self._reloj()

        self._peticiones += 1
        status, cuerpo = self._transporte(url, {"User-Agent": USER_AGENT})
        if status == 429:
            self._cuota_agotada = True
            raise CuotaAgotada(f"BCN respondió 429 para {url}")
        if status != 200:
            raise ErrorBCN(f"status {status} para {url}")
        return cuerpo
