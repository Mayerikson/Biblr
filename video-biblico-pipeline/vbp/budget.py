"""Bounded efficiency: limites explícitos por execução.

Toda ação cara (chamada de LLM, tokens, custo, tentativas, cenas, tempo) consome orçamento.
Ao estourar, a etapa vira BLOCKED com diagnóstico — nunca entra em loop silencioso.
Eficiência nunca remove controles críticos: a aprovação humana não é "economizada".
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field


class BudgetExceeded(RuntimeError):
    pass


@dataclass
class Budget:
    max_llm_calls: int = 30
    max_tokens_est: int = 200_000
    max_cost_brl: float = 5.0
    max_retries_per_stage: int = 2
    max_scenes: int = 120
    max_seconds: int = 3600
    used: dict = field(default_factory=lambda: {"llm_calls": 0, "tokens_est": 0, "cost_brl": 0.0})
    _t0: float = field(default_factory=time.monotonic)

    @classmethod
    def from_config(cls, cfg) -> "Budget":
        o = cfg.get_path("orcamento", {}) or {}
        return cls(
            max_llm_calls=int(o.get("max_chamadas_llm", 30)),
            max_tokens_est=int(o.get("max_tokens_estimados", 200_000)),
            max_cost_brl=float(o.get("max_custo_brl", 5.0)),
            max_retries_per_stage=int(o.get("max_tentativas_por_etapa", 2)),
            max_scenes=int(o.get("max_cenas", 120)),
            max_seconds=int(o.get("max_segundos_execucao", 3600)),
        )

    def check_time(self) -> None:
        elapsed = time.monotonic() - self._t0
        if elapsed > self.max_seconds:
            raise BudgetExceeded(f"tempo de execução {elapsed:.0f}s > limite {self.max_seconds}s")

    def reserve_llm(self, tokens_est: int) -> None:
        """Verifica ANTES da chamada; registra o uso só se couber."""
        self.check_time()
        if self.used["llm_calls"] + 1 > self.max_llm_calls:
            raise BudgetExceeded(f"chamadas de LLM: limite {self.max_llm_calls} atingido")
        if self.used["tokens_est"] + tokens_est > self.max_tokens_est:
            raise BudgetExceeded(
                f"tokens estimados: {self.used['tokens_est']} + {tokens_est} > limite {self.max_tokens_est}")
        self.used["llm_calls"] += 1
        self.used["tokens_est"] += tokens_est

    def add_cost(self, brl: float) -> None:
        self.used["cost_brl"] += brl
        if self.used["cost_brl"] > self.max_cost_brl:
            raise BudgetExceeded(f"custo estimado R${self.used['cost_brl']:.2f} > limite R${self.max_cost_brl:.2f}")

    def check_scenes(self, n: int) -> None:
        if n > self.max_scenes:
            raise BudgetExceeded(f"{n} cenas > limite {self.max_scenes}")

    def report(self) -> dict:
        return {
            "limits": {
                "llm_calls": self.max_llm_calls, "tokens_est": self.max_tokens_est,
                "cost_brl": self.max_cost_brl, "retries_per_stage": self.max_retries_per_stage,
                "scenes": self.max_scenes, "seconds": self.max_seconds,
            },
            "used": {k: (round(v, 4) if isinstance(v, float) else v) for k, v in self.used.items()},
            "elapsed_s": round(time.monotonic() - self._t0, 2),
        }


def estimate_tokens(text: str) -> int:
    """Estimativa conservadora (~3 caracteres por token em PT-BR). É ESTIMADO, não medido."""
    return max(1, len(text) // 3)
