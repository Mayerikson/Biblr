"""Camada de LLM portátil (model-portable).

- Provedores: openai_compat (Ollama, LM Studio, Groq, OpenRouter…), gemini, fake (testes/demonstração).
- Cadeia de fallback com circuit breaker: provedor que falha é desligado pelo resto da execução
  (padrão reaproveitado do digisystem-jobs-engine — evita repetir chamadas caras que já falharam).
- Cache por hash (provedor+modelo+temperatura+prompt): a mesma pergunta não é paga duas vezes.
- Orçamento reservado ANTES da chamada; custo estimado registrado depois.
- Nenhuma chave aparece em log: só o nome da variável de ambiente.
"""
from __future__ import annotations

import json
import re
import urllib.error
import urllib.request
from typing import Any, Callable

from .budget import Budget, BudgetExceeded, estimate_tokens
from .obs import Observer
from .state import State, sha256_text


class LLMError(RuntimeError):
    pass


# ---------------------------------------------------------------- provedores
class Provider:
    name = "base"
    model = "-"
    cost_per_1k = 0.0

    def complete(self, prompt: str, temperature: float) -> str:  # pragma: no cover - interface
        raise NotImplementedError


def _post_json(url: str, body: dict, headers: dict, timeout: int = 120) -> dict:
    req = urllib.request.Request(url, data=json.dumps(body).encode("utf-8"),
                                 headers={"Content-Type": "application/json", **headers}, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        raise LLMError(f"HTTP {exc.code} em {url.split('?')[0]}") from exc
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
        raise LLMError(f"falha de rede/JSON em {url.split('?')[0]}: {type(exc).__name__}") from exc


class OpenAICompat(Provider):
    def __init__(self, name: str, base_url: str, model: str, api_key: str = "", cost_per_1k: float = 0.0):
        self.name, self.base_url, self.model = name, base_url.rstrip("/"), model
        self.api_key, self.cost_per_1k = api_key, cost_per_1k

    def complete(self, prompt: str, temperature: float) -> str:
        headers = {"Authorization": f"Bearer {self.api_key}"} if self.api_key else {}
        data = _post_json(f"{self.base_url}/chat/completions", {
            "model": self.model, "temperature": temperature,
            "messages": [{"role": "user", "content": prompt}],
        }, headers)
        try:
            return str(data["choices"][0]["message"]["content"])
        except (KeyError, IndexError, TypeError) as exc:
            raise LLMError("resposta inesperada (openai_compat)") from exc


class Gemini(Provider):
    def __init__(self, name: str, model: str, api_key: str, cost_per_1k: float = 0.0):
        self.name, self.model, self.api_key, self.cost_per_1k = name, model, api_key, cost_per_1k

    def complete(self, prompt: str, temperature: float) -> str:
        if not self.api_key:
            raise LLMError("GEMINI sem chave configurada")
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{self.model}:generateContent"
        data = _post_json(url, {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {"temperature": temperature, "responseMimeType": "application/json"},
        }, {"x-goog-api-key": self.api_key})
        try:
            return "".join(p.get("text", "") for p in data["candidates"][0]["content"]["parts"])
        except (KeyError, IndexError, TypeError) as exc:
            raise LLMError("resposta inesperada (gemini)") from exc


class FakeProvider(Provider):
    """Provedor determinístico: responde por função. Usado em testes e em `vbp demo`."""

    def __init__(self, responder: Callable[[str], str], name: str = "fake"):
        self.name, self.model, self.responder = name, "fake-1", responder

    def complete(self, prompt: str, temperature: float) -> str:
        return self.responder(prompt)


def build_providers(cfg) -> list[Provider]:
    out: list[Provider] = []
    defs = cfg.get_path("llm.provedores", {}) or {}
    for key in cfg.get_path("llm.cadeia", []) or []:
        d = defs.get(key)
        if not d:
            continue
        api_key = cfg.secret(d.get("api_key_env", ""))
        cost = float(d.get("custo_por_1k_tokens_brl", 0.0))
        if d.get("tipo") == "openai_compat":
            out.append(OpenAICompat(key, d["base_url"], d["modelo"], api_key, cost))
        elif d.get("tipo") == "gemini":
            out.append(Gemini(key, d["modelo"], api_key, cost))
    return out


# ---------------------------------------------------------------- cliente
def extract_json(text: str) -> Any:
    """Aceita JSON puro, bloco ```json``` ou o primeiro objeto/lista balanceado no texto."""
    text = text.strip()
    fence = re.search(r"```(?:json)?\s*(.+?)```", text, re.S)
    if fence:
        text = fence.group(1).strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    for open_ch, close_ch in (("{", "}"), ("[", "]")):
        start = text.find(open_ch)
        while start != -1:
            depth, in_str, esc = 0, False, False
            for i in range(start, len(text)):
                ch = text[i]
                if in_str:
                    esc = (ch == "\\") and not esc
                    if ch == '"' and not esc:
                        in_str = False
                    continue
                if ch == '"':
                    in_str = True
                elif ch == open_ch:
                    depth += 1
                elif ch == close_ch:
                    depth -= 1
                    if depth == 0:
                        try:
                            return json.loads(text[start:i + 1])
                        except json.JSONDecodeError:
                            break
            start = text.find(open_ch, start + 1)
    raise LLMError("resposta sem JSON válido")


class LLMClient:
    def __init__(self, providers: list[Provider], state: State, obs: Observer, budget: Budget):
        if not providers:
            raise LLMError("nenhum provedor de LLM configurado (veja [llm] no TOML)")
        self.providers, self.state, self.obs, self.budget = providers, state, obs, budget
        self.broken: set[str] = set()

    def json(self, prompt: str, *, temperature: float, stage: str, episode: str | None = None,
             use_cache: bool = True) -> tuple[Any, dict]:
        """Retorna (dados, proveniência). Proveniência entra no .explain.json do artefato."""
        last_err = ""
        for idx, prov in enumerate(self.providers):
            if prov.name in self.broken:
                continue
            key = sha256_text(prov.name, prov.model, f"{temperature:.2f}", prompt)
            cached = self.state.cache_get(key) if use_cache else None
            if cached is not None:
                self.obs.count("llm_cache_hits")
                self.obs.event("llm_cache_hit", episode=episode, stage=stage, provider=prov.name)
                try:
                    return extract_json(cached), {"provider": prov.name, "model": prov.model, "cache": True, "key": key}
                except LLMError:
                    pass  # cache corrompido: segue para chamada real
            tokens = estimate_tokens(prompt) + 2000  # entrada + margem de saída (ESTIMADO)
            self.budget.reserve_llm(tokens)  # BudgetExceeded propaga: etapa vira BLOCKED
            self.obs.count("llm_calls")
            self.obs.count("tokens_est", tokens)
            try:
                raw = prov.complete(prompt, temperature)
                data = extract_json(raw)
            except LLMError as exc:
                self.broken.add(prov.name)
                self.obs.count("llm_failures")
                last_err = str(exc)
                self.obs.event("llm_failure", episode=episode, stage=stage, status="FAIL",
                               provider=prov.name, error=last_err)
                if idx + 1 < len(self.providers):
                    self.obs.count("fallbacks")
                continue
            cost = tokens / 1000 * prov.cost_per_1k
            self.obs.count("cost_brl_est", cost)
            self.budget.add_cost(cost)
            self.state.cache_put(key, prov.name, prov.model, raw)
            self.obs.event("llm_call", episode=episode, stage=stage, provider=prov.name,
                           model=prov.model, tokens_est=tokens, cost_brl_est=round(cost, 4))
            return data, {"provider": prov.name, "model": prov.model, "cache": False, "key": key,
                          "tokens_est": tokens, "cost_brl_est": round(cost, 4)}
        raise LLMError(f"todos os provedores falharam; último erro: {last_err or 'nenhum disponível'}")


__all__ = ["LLMClient", "LLMError", "FakeProvider", "OpenAICompat", "Gemini", "build_providers",
           "extract_json", "BudgetExceeded"]
