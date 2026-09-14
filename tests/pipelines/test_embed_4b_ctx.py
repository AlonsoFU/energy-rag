"""El embedder 4B siempre pide num_ctx chico (2026-09-14).

Sin num_ctx, Ollama cargaba qwen3-embedding:4b con 32768 de contexto: 9.8 GB de RAM en CPU, y el
sistema mataba las corridas. Con 4096 los vectores son identicos en el mismo dispositivo.
"""
import io, json
import urllib.request

import pytest

from src.core import config as cfg
from src.pipelines.retrieve import _embed_4b_query


class _Resp(io.BytesIO):
    def __enter__(self): return self
    def __exit__(self, *a): return False


@pytest.fixture
def capturar(monkeypatch):
    enviados = []
    def fake_urlopen(req, *a, **k):
        enviados.append(json.loads(req.data))
        return _Resp(json.dumps({"embeddings": [[0.1, 0.2, 0.3]]}).encode())
    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    return enviados


@pytest.mark.parametrize("cpu", [False, True])
def test_siempre_manda_num_ctx(capturar, monkeypatch, cpu):
    monkeypatch.setattr(cfg.settings, "embed_4b_cpu", cpu, raising=False)
    assert _embed_4b_query("hola") == [0.1, 0.2, 0.3]
    opts = capturar[-1]["options"]
    assert opts["num_ctx"] == 4096
    assert ("num_gpu" in opts) == cpu


def test_num_ctx_configurable(capturar, monkeypatch):
    monkeypatch.setattr(cfg.settings, "embed_4b_num_ctx", 2048, raising=False)
    _embed_4b_query("hola")
    assert capturar[-1]["options"]["num_ctx"] == 2048
