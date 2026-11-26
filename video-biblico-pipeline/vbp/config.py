"""Carregamento de configuração (TOML + variáveis de ambiente).

Ordem de precedência: overrides passados em código > config/pipeline.toml > config/pipeline.example.toml.
Segredos nunca vêm do TOML: o TOML só indica o NOME da variável de ambiente (ex.: api_key_env).
"""
from __future__ import annotations

import copy
import os
import tomllib
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
EXAMPLE = ROOT / "config" / "pipeline.example.toml"
LOCAL = ROOT / "config" / "pipeline.toml"


def _deep_merge(base: dict, extra: dict) -> dict:
    out = copy.deepcopy(base)
    for key, value in extra.items():
        if isinstance(value, dict) and isinstance(out.get(key), dict):
            out[key] = _deep_merge(out[key], value)
        else:
            out[key] = copy.deepcopy(value)
    return out


def load_dotenv(path: Path | None = None) -> None:
    """Lê um .env simples (CHAVE=valor) sem sobrescrever variáveis já definidas."""
    path = path or ROOT / ".env"
    if not path.is_file():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


class Config(dict):
    """Dicionário com acesso por caminho: cfg.get_path('video.fps')."""

    def get_path(self, dotted: str, default: Any = None) -> Any:
        node: Any = self
        for part in dotted.split("."):
            if not isinstance(node, dict) or part not in node:
                return default
            node = node[part]
        return node

    @property
    def workspace(self) -> Path:
        ws = Path(self.get_path("geral.workspace", "workspace"))
        return ws if ws.is_absolute() else ROOT / ws

    def secret(self, env_name: str) -> str:
        return os.environ.get(env_name, "").strip() if env_name else ""


def load_config(path: Path | None = None, overrides: dict | None = None) -> Config:
    load_dotenv()
    with EXAMPLE.open("rb") as fh:
        data = tomllib.load(fh)
    target = path or LOCAL
    if target.is_file():
        with target.open("rb") as fh:
            data = _deep_merge(data, tomllib.load(fh))
    if overrides:
        data = _deep_merge(data, overrides)
    return Config(data)
