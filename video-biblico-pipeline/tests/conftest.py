import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from vbp.config import load_config  # noqa: E402
from vbp.demo import responder  # noqa: E402
from vbp.llm import FakeProvider  # noqa: E402
from vbp.pipeline import Pipeline  # noqa: E402


@pytest.fixture
def cfg(tmp_path):
    return load_config(path=tmp_path / "nao-existe.toml", overrides={
        "geral": {"workspace": str(tmp_path / "ws")},
        "video": {"largura": 320, "altura": 180, "fps": 10, "duracao_alvo_min": 1,
                  "palavras_por_minuto": 600, "palavras_por_cena": 30},
        "imagens": {"provedor": "placeholder"}, "narracao": {"provedor": "silencio"},
    })


class SpyProvider(FakeProvider):
    """FakeProvider que registra os prompts recebidos (para verificar feedback e cache)."""

    def __init__(self, fn=responder, name="fake"):
        super().__init__(fn, name=name)
        self.prompts = []

    def complete(self, prompt, temperature):
        self.prompts.append(prompt)
        return super().complete(prompt, temperature)


@pytest.fixture
def make_pipeline(cfg):
    def _make(providers=None, live=False, config=None):
        return Pipeline(config or cfg, providers=providers or [SpyProvider()], live=live, echo=False)
    return _make


@pytest.fixture
def episode():
    return ("EP001", "Davi e Golias", "coragem", "1 Samuel 17:4-11; 1 Samuel 17:45-47", "Davi; Golias")
