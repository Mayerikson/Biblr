"""Observabilidade e explicabilidade.

- Cada execução tem um run_id (correlation ID) que aparece em todo evento.
- Eventos são JSON Lines em workspace/runs/<run_id>/events.jsonl (e espelhados no SQLite via sink).
- span() mede duração e status (PASS/FAIL/BLOCKED/SKIPPED) de cada etapa.
- Métricas (chamadas de LLM, cache, tokens, custo, tentativas) vão para run_summary.json.
- explain() grava, ao lado de cada artefato, POR QUE cada decisão foi tomada (<artefato>.explain.json).
- redact() remove segredos antes de qualquer gravação.
"""
from __future__ import annotations

import json
import re
import secrets
import sys
import time
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Iterator
from zoneinfo import ZoneInfo

TZ = ZoneInfo("America/Sao_Paulo")
SECRET_KEY = re.compile(r"(key|token|secret|senha|password|authorization)", re.I)
SECRET_VALUE = re.compile(r"(AIza[0-9A-Za-z_\-]{20,}|gsk_[0-9A-Za-z]{20,}|sk-[0-9A-Za-z_\-]{20,}|\d{8,10}:[A-Za-z0-9_\-]{30,})")

STATUS = ("PASS", "FAIL", "BLOCKED", "SKIPPED", "NOT_RUN")


def now_iso() -> str:
    return datetime.now(TZ).isoformat(timespec="seconds")


def new_run_id() -> str:
    return datetime.now(TZ).strftime("%Y%m%d-%H%M%S") + "-" + secrets.token_hex(3)


def redact(value: Any) -> Any:
    if isinstance(value, dict):
        return {k: ("***" if SECRET_KEY.search(str(k)) and v else redact(v)) for k, v in value.items()}
    if isinstance(value, list):
        return [redact(v) for v in value]
    if isinstance(value, str):
        return SECRET_VALUE.sub("***", value)
    return value


class StageResult(Exception):
    """Interrompe uma etapa com status explícito (BLOCKED/SKIPPED) sem ser tratada como erro inesperado."""

    def __init__(self, status: str, reason: str):
        super().__init__(reason)
        self.status = status
        self.reason = reason


class Observer:
    def __init__(self, runs_dir: Path, mode: str = "DRY_RUN", run_id: str | None = None, echo: bool = True):
        self.run_id = run_id or new_run_id()
        self.mode = mode
        self.dir = Path(runs_dir) / self.run_id
        self.dir.mkdir(parents=True, exist_ok=True)
        self.events_path = self.dir / "events.jsonl"
        self.started = time.monotonic()
        self.started_at = now_iso()
        self.echo = echo
        self.sinks: list[Callable[[dict], None]] = []
        self.metrics: dict[str, float] = {
            "llm_calls": 0, "llm_cache_hits": 0, "llm_failures": 0, "tokens_est": 0,
            "cost_brl_est": 0.0, "retries": 0, "fallbacks": 0,
        }
        self.stages: list[dict] = []

    # ---- eventos -------------------------------------------------------
    def event(self, event: str, *, episode: str | None = None, stage: str | None = None,
              status: str | None = None, **data: Any) -> dict:
        record = {"ts": now_iso(), "run_id": self.run_id, "mode": self.mode, "event": event}
        if episode:
            record["episode"] = episode
        if stage:
            record["stage"] = stage
        if status:
            record["status"] = status
        if data:
            record["data"] = redact(data)
        with self.events_path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(record, ensure_ascii=False) + "\n")
        for sink in self.sinks:
            try:
                sink(record)
            except Exception:  # um sink com defeito nunca derruba o pipeline
                pass
        if self.echo:
            tag = f"[{record.get('status', 'INFO')}]"
            where = "/".join(x for x in (episode, stage) if x)
            print(f"{tag:10} {where:28} {event}", file=sys.stderr)
        return record

    def count(self, metric: str, amount: float = 1) -> None:
        self.metrics[metric] = self.metrics.get(metric, 0) + amount

    @contextmanager
    def span(self, stage: str, episode: str | None = None) -> Iterator[dict]:
        info: dict[str, Any] = {"stage": stage, "episode": episode, "status": "PASS", "reason": ""}
        t0 = time.monotonic()
        self.event("stage_start", episode=episode, stage=stage)
        try:
            yield info
        except StageResult as res:
            info["status"], info["reason"] = res.status, res.reason
        except Exception as exc:  # erro inesperado: registra tipo e mensagem redigida, sem stack de segredos
            info["status"], info["reason"] = "FAIL", f"{type(exc).__name__}: {redact(str(exc))[:500]}"
        finally:
            info["duration_ms"] = int((time.monotonic() - t0) * 1000)
            self.stages.append(dict(info))
            self.event("stage_end", episode=episode, stage=stage, status=info["status"],
                       duration_ms=info["duration_ms"], reason=info["reason"])

    # ---- explicabilidade ----------------------------------------------
    @staticmethod
    def explain(artifact: Path, decisions: dict) -> Path:
        """Grava <artefato>.explain.json com as decisões e seus motivos."""
        target = artifact.with_suffix(artifact.suffix + ".explain.json")
        payload = {"artifact": artifact.name, "generated_at": now_iso(), **redact(decisions)}
        target.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        return target

    # ---- resumo --------------------------------------------------------
    def summary(self, budget: dict | None = None) -> dict:
        counts: dict[str, int] = {}
        for st in self.stages:
            counts[st["status"]] = counts.get(st["status"], 0) + 1
        overall = "PASS"
        if counts.get("FAIL"):
            overall = "FAIL"
        elif counts.get("BLOCKED"):
            overall = "BLOCKED"
        data = {
            "run_id": self.run_id, "mode": self.mode, "status": overall,
            "started_at": self.started_at, "finished_at": now_iso(),
            "duration_s": round(time.monotonic() - self.started, 2),
            "stage_counts": counts, "stages": self.stages,
            "metrics": {k: (round(v, 4) if isinstance(v, float) else v) for k, v in self.metrics.items()},
            "budget": budget or {},
        }
        (self.dir / "run_summary.json").write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        return data
