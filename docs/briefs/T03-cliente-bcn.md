# Brief T03 — Cliente BCN con intervalo, 429 y lista de hosts

Contrato: [`contrato.md`](contrato.md) · Spec: `docs/specs/cambios_dia-h1-reconocer-lo-nuevo.md`
· Cubre H1-CA-23, 27, 28.

## Objetivo

Un único punto de salida a red para la historia, que respete el intervalo entre peticiones,
corte de forma ordenada ante un 429 y rechace hosts no permitidos.

## Archivos

- Crear `src/descubrimiento/cliente_bcn.py`
- Crear `tests/descubrimiento/test_cliente_bcn.py`

Ningún otro archivo.

## Qué hacer

1. Clase `ClienteBCN(intervalo=20.0, transporte=None, reloj=None, dormir=None)`.
   - `transporte`: callable `(url, headers) -> (status: int, cuerpo: bytes)`. Por defecto,
     uno hecho con `urllib.request` (biblioteca estándar) que envía un `User-Agent` de
     navegador y devuelve el status también en respuestas de error HTTP.
   - `reloj` y `dormir`: por defecto `time.monotonic` y `time.sleep`; inyectables.
2. Método `obtener(url) -> bytes`:
   - Si el host no está en la lista de la sección 5 del contrato, lanza `HostNoPermitido`
     **antes** de llamar al transporte. Comparación exacta de host, no por subcadena.
   - Espera lo necesario para que entre el inicio de dos peticiones consecutivas pasen al
     menos `intervalo` segundos.
   - Con status 429 lanza `CuotaAgotada`. Tras eso, toda llamada posterior de la misma
     instancia lanza `CuotaAgotada` sin llamar al transporte.
   - Con otro status distinto de 200 lanza `ErrorBCN` con el status y la URL.
3. Propiedad `peticiones` con la cantidad de llamadas hechas al transporte.
4. Las tres excepciones heredan de una base `ErrorBCN`.

## Tests

Todos con transporte, reloj y `dormir` simulados. Ninguno toca la red.

- Dos peticiones seguidas: `dormir` recibe el tiempo que falta para completar el intervalo.
- Si ya pasó el intervalo, no se duerme.
- Host ajeno (`example.com`) y host tramposo (`bcn.cl.evil.com`, `evilbcn.cl`): se rechazan
  y el transporte no se llama.
- Cada host permitido del contrato pasa.
- 429: lanza `CuotaAgotada`; la llamada siguiente también y `peticiones` no aumenta.
- Status 500: lanza `ErrorBCN` y la instancia sigue utilizable.

## Terminado cuando

Los tests pasan con el entorno indicado.

## Fuera de alcance

Reintentos, caché, Playwright, parseo de respuestas, y hacer cualquier petición real.

## Entorno

`PYTHONPATH=. /home/alonso/.claude/jobs/6224a57d/tmp/venv/bin/python -m pytest tests/descubrimiento/test_cliente_bcn.py -q`
(si `tests/conftest.py` impide la colección por falta de un paquete, repórtalo; no lo edites).
