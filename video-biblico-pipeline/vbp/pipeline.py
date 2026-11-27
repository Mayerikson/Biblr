"""Orquestrador: executa as etapas de um episódio com estado, idempotência, orçamento e observabilidade.

PAUTA → ROTEIRO → STORYBOARD → [gate humano] → IMAGENS → NARRACAO → RENDER → PUBLICACAO

Cada etapa:
- calcula o hash das entradas; se o artefato existe com o mesmo hash → SKIPPED (não refaz nem paga de novo);
- roda dentro de obs.span() (duração, status, motivo, run_id);
- grava <artefato>.explain.json com as decisões;
- respeita o orçamento (BudgetExceeded → BLOCKED com diagnóstico).
"""
from __future__ import annotations

import json
from pathlib import Path

from . import approval, media, publish, script as script_mod, storyboard as sb_mod
from .budget import Budget, BudgetExceeded
from .config import ROOT, Config
from .llm import LLMClient, LLMError, Provider, build_providers
from .obs import Observer, StageResult
from .state import State, sha256_text

STORYBOARD_RULES_VERSION = "2"  # mude ao alterar SHOT_RULES: invalida storyboards antigos


class Pipeline:
    def __init__(self, cfg: Config, providers: list[Provider] | None = None, live: bool = False, echo: bool = True):
        self.cfg = cfg
        self.live = live
        self.ws = cfg.workspace
        self.ws.mkdir(parents=True, exist_ok=True)
        self.state = State(self.ws / "estado.sqlite3")
        self.obs = Observer(self.ws / "runs", mode="LIVE" if live else "DRY_RUN", echo=echo)
        self.obs.sinks.append(self.state.append_event)
        self.budget = Budget.from_config(cfg)
        self._providers = providers
        self._llm: LLMClient | None = None

    # ------------------------------------------------------------ utilidades
    @property
    def llm(self) -> LLMClient:
        if self._llm is None:
            provs = self._providers if self._providers is not None else build_providers(self.cfg)
            self._llm = LLMClient(provs, self.state, self.obs, self.budget)
        return self._llm

    def ep_dir(self, ep_id: str) -> Path:
        return self.ws / "episodios" / ep_id

    def _prompt_files_hash(self, *names: str) -> str:
        return sha256_text(*[(ROOT / "prompts" / n).read_text(encoding="utf-8") for n in names])

    def _cfg_hash(self, *paths: str) -> str:
        return sha256_text(*[json.dumps(self.cfg.get_path(p), sort_keys=True, ensure_ascii=False) for p in paths])

    # ------------------------------------------------------------ execução
    def run(self, ep_id: str, until: str | None = None, publish_at: str | None = None) -> dict:
        ep = self.state.episode(ep_id)
        if not ep:
            raise ValueError(f"episódio {ep_id} não existe (use import-pauta ou add)")
        stages = [("ROTEIRO", self.stage_script), ("STORYBOARD", self.stage_storyboard),
                  ("APROVACAO", self.stage_gate), ("IMAGENS", self.stage_images),
                  ("NARRACAO", self.stage_narration), ("RENDER", self.stage_render),
                  ("PUBLICACAO", lambda e, i: self.stage_publish(e, i, publish_at))]
        self.obs.event("run_start", episode=ep_id, until=until, live=self.live)
        for name, fn in stages:
            with self.obs.span(name, ep_id) as info:
                try:
                    fn(ep, info)
                except BudgetExceeded as exc:
                    self._diagnose(ep_id, name, f"orçamento: {exc}")
                    raise StageResult("BLOCKED", f"orçamento estourado: {exc}") from exc
            if info["status"] in ("FAIL", "BLOCKED"):
                if info["status"] == "FAIL":
                    self._diagnose(ep_id, name, info["reason"])
                break
            if until and name == until.upper():
                break
        return self.obs.summary(self.budget.report())

    def _diagnose(self, ep_id: str, stage: str, reason: str) -> None:
        d = self.ep_dir(ep_id)
        d.mkdir(parents=True, exist_ok=True)
        (d / f"diagnostico_{stage.lower()}.json").write_text(json.dumps({
            "run_id": self.obs.run_id, "etapa": stage, "motivo": reason,
            "orcamento": self.budget.report(), "metricas": self.obs.metrics,
            "proximo_passo": "leia o motivo, ajuste config/prompt/arquivos e rode de novo; etapas prontas serão puladas",
        }, ensure_ascii=False, indent=2), encoding="utf-8")

    # ------------------------------------------------------------ ROTEIRO
    def stage_script(self, ep: dict, info: dict) -> None:
        d = self.ep_dir(ep["id"])
        # Só campos de conteúdo entram no hash (status/updated_at não), para a idempotência ser estável.
        in_hash = sha256_text(ep["id"], ep["titulo"], ep["tema"], ep["referencias"], ep["personagens"],
                              self._prompt_files_hash("roteiro.md", "editorial.md"),
                              self._cfg_hash("roteiro", "video.duracao_alvo_min", "video.palavras_por_minuto"))
        feedback = ""
        human = False
        last = self.state.latest_approval(ep["id"])
        if last and last["decision"] == "AJUSTE_SOLICITADO" and last["content_hash"] == approval.content_hash(d):
            feedback = f"- Pedido do revisor humano: {last.get('note')}"  # ajuste humano força nova versão
            human = True
        elif self.state.is_fresh(ep["id"], "ROTEIRO", in_hash):
            raise StageResult("SKIPPED", "roteiro já existe para as mesmas entradas")
        attempts = []
        max_try = self.budget.max_retries_per_stage
        for attempt in range(1, max_try + 1):
            prompt = script_mod.build_prompt(ep, self.cfg, feedback)
            try:
                data, prov = self.llm.json(prompt, temperature=float(self.cfg.get_path("llm.temperatura_roteiro", 0.7)),
                                           stage="ROTEIRO", episode=ep["id"],
                                           use_cache=not (human and attempt == 1))
            except LLMError as exc:
                raise StageResult("BLOCKED", f"LLM indisponível: {exc}") from exc
            checks = script_mod.validate_script(data, self.cfg)
            bad = script_mod.failed(checks)
            attempts.append({"tentativa": attempt, "proveniencia": prov, "checks": checks})
            if not bad:
                path = script_mod.save_script(d, data)
                self.state.save_artifact(ep["id"], "ROTEIRO", path, in_hash)
                self.state.set_status(ep["id"], "ROTEIRO")
                Observer.explain(path, {"etapa": "ROTEIRO", "run_id": self.obs.run_id, "tentativas": attempts,
                                        "feedback_humano": feedback or None,
                                        "palavras": script_mod.word_count(script_mod.full_text(data))})
                return
            if prov.get("key"):
                self.state.cache_delete(prov["key"])  # resposta reprovada não pode voltar do cache
            feedback = "\n".join(f"- {c['check']}: {c['detail']}" for c in bad)
            if attempt < max_try:
                self.obs.count("retries")
                self.obs.event("script_retry", episode=ep["id"], stage="ROTEIRO", status="FAIL",
                               tentativa=attempt, falhas=[c["check"] for c in bad])
        d.mkdir(parents=True, exist_ok=True)
        (d / "roteiro.rejeitado.json").write_text(json.dumps(attempts, ensure_ascii=False, indent=2), encoding="utf-8")
        self._diagnose(ep["id"], "ROTEIRO", f"validação falhou após {max_try} tentativas: {feedback}")
        raise StageResult("BLOCKED", f"roteiro reprovado na validação após {max_try} tentativas")

    # ------------------------------------------------------------ STORYBOARD
    def stage_storyboard(self, ep: dict, info: dict) -> None:
        d = self.ep_dir(ep["id"])
        roteiro = d / "roteiro.json"
        in_hash = sha256_text(roteiro.read_text(encoding="utf-8"), STORYBOARD_RULES_VERSION,
                              self._cfg_hash("personagens", "imagens.estilo", "video.palavras_por_cena", "storyboard"),
                              self._prompt_files_hash("storyboard.md"))
        if self.state.is_fresh(ep["id"], "STORYBOARD", in_hash):
            raise StageResult("SKIPPED", "storyboard já existe para o roteiro atual")
        script = json.loads(roteiro.read_text(encoding="utf-8"))
        board, explain = sb_mod.build_storyboard(script, self.cfg)
        self.budget.check_scenes(len(board["cenas"]))
        explain["llm_descricoes"] = "desligado"
        if self.cfg.get_path("storyboard.usar_llm", True):
            try:
                desc, prov = self.llm.json(sb_mod.storyboard_prompt(board, self.cfg, ROOT),
                                           temperature=float(self.cfg.get_path("llm.temperatura_storyboard", 0.3)),
                                           stage="STORYBOARD", episode=ep["id"])
                n = sb_mod.apply_llm_descriptions(board, desc, self.cfg.get_path("imagens.estilo", ""))
                explain["llm_descricoes"] = {"cenas_atualizadas": n, "proveniencia": prov}
            except (LLMError, BudgetExceeded, AttributeError, TypeError, ValueError) as exc:  # degradação graciosa: regras continuam valendo
                explain["llm_descricoes"] = f"falhou, mantidas descrições por regra: {exc}"
        path = d / "storyboard.json"
        path.write_text(json.dumps(board, ensure_ascii=False, indent=2), encoding="utf-8")
        Observer.explain(path, {"etapa": "STORYBOARD", "run_id": self.obs.run_id, **explain})
        self.state.save_artifact(ep["id"], "STORYBOARD", path, in_hash)
        self.state.set_status(ep["id"], "STORYBOARD")

    # ------------------------------------------------------------ GATE HUMANO
    def stage_gate(self, ep: dict, info: dict) -> None:
        d = self.ep_dir(ep["id"])
        ok, why = approval.is_approved(self.state, ep["id"], d)
        if ok:
            self.state.set_status(ep["id"], "APROVADO")
            info["reason"] = why
            return
        self.state.set_status(ep["id"], "AGUARDANDO_APROVACAO")
        (d / "REVISAO.txt").write_text(approval.review_summary(ep["id"], d), encoding="utf-8")
        raise StageResult("BLOCKED", f"aguardando revisão humana ({why}). Veja {d / 'roteiro.md'} e prompts/revisao.md")

    # ------------------------------------------------------------ MÍDIA
    def _board(self, ep_id: str) -> dict:
        return json.loads((self.ep_dir(ep_id) / "storyboard.json").read_text(encoding="utf-8"))

    def stage_images(self, ep: dict, info: dict) -> None:
        result = media.make_images(self._board(ep["id"]), self.ep_dir(ep["id"]), self.cfg)
        info["reason"] = f"{result['geradas']} geradas, {result['reaproveitadas']} reaproveitadas"
        self.obs.event("images_done", episode=ep["id"], stage="IMAGENS", **result)
        self.state.set_status(ep["id"], "IMAGENS")

    def stage_narration(self, ep: dict, info: dict) -> None:
        result = media.make_narration(self._board(ep["id"]), self.ep_dir(ep["id"]), self.cfg)
        info["reason"] = f"{result['geradas']} geradas, {result['reaproveitadas']} reaproveitadas"
        self.obs.event("narration_done", episode=ep["id"], stage="NARRACAO", **result)
        self.state.set_status(ep["id"], "NARRACAO")

    def stage_render(self, ep: dict, info: dict) -> None:
        d = self.ep_dir(ep["id"])
        result = media.render(self._board(ep["id"]), d, self.cfg)
        Observer.explain(d / "video.mp4", {"etapa": "RENDER", "run_id": self.obs.run_id, **result,
                                           "movimentos": "por plano, ver vbp/storyboard.py::SHOT_MOTION"})
        self.state.save_artifact(ep["id"], "RENDER", d / "video.mp4", approval.content_hash(d))
        self.state.set_status(ep["id"], "PRONTO")
        info["reason"] = f"{result['cenas']} cenas, {result['duracao_s']}s"

    def stage_publish(self, ep: dict, info: dict, publish_at: str | None) -> None:
        d = self.ep_dir(ep["id"])
        ok, why = approval.is_approved(self.state, ep["id"], d)
        if not ok:  # defesa em profundidade: nunca publica sem aprovação válida
            raise StageResult("BLOCKED", f"publicação exige aprovação válida: {why}")
        key = f"youtube_video:{ep['id']}"
        sent = self.state.kv_get(key)
        if sent:  # nunca envia o mesmo episódio duas vezes
            self.state.set_status(ep["id"], "PUBLICADO")
            raise StageResult("SKIPPED", f"episódio já enviado ao YouTube: {sent}")
        plan = publish.publish(d, self.cfg, live=self.live, publish_at=publish_at,
                               on_uploaded=lambda vid: self.state.kv_set(key, vid))
        if plan.get("video_id"):
            self.state.set_status(ep["id"], "PUBLICADO")
            info["reason"] = f"enviado como privado/agendado: {plan['video_id']}"
        else:
            info["reason"] = "DRY_RUN: publish_plan.json gerado; nada foi enviado"
            if plan.get("pendencias_licenca"):
                info["reason"] += f" ({len(plan['pendencias_licenca'])} licença(s) pendente(s); --live será bloqueado)"
