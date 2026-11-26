"""Interface de linha de comando: python scripts/vbp.py <comando>."""
from __future__ import annotations

import argparse
import csv
import json
import os
import platform
import shutil
import sys
from pathlib import Path

from . import __version__, approval
from .config import ROOT, load_config
from .llm import FakeProvider
from .pipeline import Pipeline
from .state import State


def _state(cfg) -> State:
    cfg.workspace.mkdir(parents=True, exist_ok=True)
    return State(cfg.workspace / "estado.sqlite3")


def _print(obj) -> None:
    print(json.dumps(obj, ensure_ascii=False, indent=2))


def cmd_init(cfg, args) -> int:
    local = ROOT / "config" / "pipeline.toml"
    if not local.exists():
        shutil.copy(ROOT / "config" / "pipeline.example.toml", local)
        print(f"criado {local} — ajuste provedores e estilo")
    env = ROOT / ".env"
    if not env.exists():
        shutil.copy(ROOT / ".env.example", env)
        print(f"criado {env} — coloque suas chaves aqui (nunca suba para o Git)")
    _state(cfg)
    print(f"workspace pronto em {cfg.workspace}")
    return 0


def cmd_doctor(cfg, args) -> int:
    """Health check: PASS/FAIL/NOT_RUN por item. Não testa provedores pagos (custo)."""
    checks = []

    def add(item, status, detail=""):
        checks.append({"item": item, "status": status, "detalhe": detail})

    add("python>=3.11", "PASS" if sys.version_info >= (3, 11) else "FAIL", platform.python_version())
    add("ffmpeg", "PASS" if shutil.which("ffmpeg") else "FAIL", shutil.which("ffmpeg") or "instale o ffmpeg")
    add("ffprobe", "PASS" if shutil.which("ffprobe") else "FAIL", shutil.which("ffprobe") or "vem junto com o ffmpeg")
    try:
        import PIL  # noqa: F401
        add("Pillow (thumbnail/placeholder)", "PASS")
    except ImportError:
        add("Pillow (thumbnail/placeholder)", "NOT_RUN", "opcional: pip install Pillow")
    add("config local", "PASS" if (ROOT / "config" / "pipeline.toml").exists() else "NOT_RUN",
        "usando pipeline.example.toml" if not (ROOT / "config" / "pipeline.toml").exists() else "")
    for key in cfg.get_path("llm.cadeia", []):
        d = cfg.get_path(f"llm.provedores.{key}", {}) or {}
        env = d.get("api_key_env", "")
        if env:
            add(f"LLM {key}: chave {env}", "PASS" if os.environ.get(env) else "FAIL", "definida" if os.environ.get(env) else "ausente no .env")
        else:
            add(f"LLM {key}: {d.get('base_url', '')}", "NOT_RUN", "local; teste com `vbp run` (conexão não verificada aqui)")
    try:
        _state(cfg)
        add("workspace gravável", "PASS", str(cfg.workspace))
    except OSError as exc:
        add("workspace gravável", "FAIL", str(exc))
    _print(checks)
    return 1 if any(c["status"] == "FAIL" for c in checks if c["item"] in ("ffmpeg", "ffprobe", "python>=3.11")) else 0


def cmd_add(cfg, args) -> int:
    ok = _state(cfg).add_episode(args.id.upper(), args.titulo, args.tema, args.referencias, args.personagens or "")
    print("inserido" if ok else "já existia (nada alterado)")
    return 0


def cmd_import(cfg, args) -> int:
    st, n_new, n_old = _state(cfg), 0, 0
    with open(args.csv, encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            if st.add_episode(row["id"].strip().upper(), row["titulo"].strip(), row["tema"].strip(),
                              row["referencias"].strip(), row.get("personagens", "").strip()):
                n_new += 1
            else:
                n_old += 1
    print(f"{n_new} novo(s), {n_old} já existente(s)")
    return 0


def cmd_status(cfg, args) -> int:
    st = _state(cfg)
    for ep in st.episodes():
        ok, why = approval.is_approved(st, ep["id"], cfg.workspace / "episodios" / ep["id"])
        print(f"{ep['id']:8} {ep['status']:22} aprovação: {'OK' if ok else why[:60]:62} {ep['titulo']}")
    return 0


def _pipeline(cfg, args, demo: bool = False) -> Pipeline:
    providers = [FakeProvider(__import__("vbp.demo", fromlist=["responder"]).responder)] if demo or args.fake_llm else None
    return Pipeline(cfg, providers=providers, live=getattr(args, "live", False))


def cmd_run(cfg, args) -> int:
    pipe = _pipeline(cfg, args)
    ids = [args.episode.upper()] if args.episode else [e["id"] for e in pipe.state.episodes()
                                                       if e["status"] not in ("PUBLICADO",)]
    rc = 0
    for ep_id in ids:
        summary = pipe.run(ep_id, until=args.until, publish_at=args.publicar_em)
        print(f"\n{ep_id}: {summary['status']}  (run {summary['run_id']}, resumo em {pipe.obs.dir / 'run_summary.json'})")
        rc = rc or (1 if summary["status"] == "FAIL" else 0)
    return rc


def cmd_approve(cfg, args) -> int:
    h = approval.approve(_state(cfg), args.id.upper(), cfg.workspace / "episodios" / args.id.upper(), args.por, args.nota or "")
    print(f"aprovado; conteúdo selado com sha256 {h[:16]}…")
    return 0


def cmd_reject(cfg, args) -> int:
    approval.request_changes(_state(cfg), args.id.upper(), cfg.workspace / "episodios" / args.id.upper(), args.por, args.motivo)
    print("ajuste registrado; no próximo `run` o roteiro será refeito com esse pedido")
    return 0


def cmd_explain(cfg, args) -> int:
    d = cfg.workspace / "episodios" / args.id.upper()
    for f in sorted(d.glob("*.explain.json")):
        print(f"\n=== {f.name}")
        print(f.read_text(encoding="utf-8")[:6000])
    for f in sorted(d.glob("diagnostico_*.json")):
        print(f"\n=== {f.name}")
        print(f.read_text(encoding="utf-8"))
    if args.timeline:
        print("\n=== linha do tempo")
        for ev in _state(cfg).timeline(args.id.upper()):
            print(f"{ev['ts']} {ev['run_id']} {ev['stage'] or '-':12} {ev['event']:16} {ev['status'] or ''}")
    return 0


def cmd_report(cfg, args) -> int:
    runs = sorted((cfg.workspace / "runs").glob("*/run_summary.json"))[-args.ultimos:]
    rows = []
    for p in runs:
        s = json.loads(p.read_text(encoding="utf-8"))
        m = s["metrics"]
        rows.append({"run_id": s["run_id"], "modo": s["mode"], "status": s["status"], "duracao_s": s["duration_s"],
                     "etapas": s["stage_counts"], "llm_calls": m.get("llm_calls"), "cache_hits": m.get("llm_cache_hits"),
                     "tokens_est": m.get("tokens_est"), "custo_brl_est": m.get("cost_brl_est"),
                     "retries": m.get("retries"), "fallbacks": m.get("fallbacks")})
    _print(rows)
    return 0


def cmd_tg_review(cfg, args) -> int:
    tg = _telegram(cfg)
    ep_id = args.id.upper()
    tg.send(approval.review_summary(ep_id, cfg.workspace / "episodios" / ep_id))
    print("resumo enviado para revisão no Telegram")
    return 0


def cmd_tg_poll(cfg, args) -> int:
    handled = _telegram(cfg).poll_once(_state(cfg), cfg.workspace)
    print("\n".join(handled) or "nenhum comando novo")
    return 0


def _telegram(cfg) -> approval.Telegram:
    token = cfg.secret(cfg.get_path("aprovacao.telegram_token_env", "TELEGRAM_BOT_TOKEN"))
    ids_raw = cfg.secret(cfg.get_path("aprovacao.telegram_chat_ids_env", "TELEGRAM_ALLOWED_CHAT_IDS"))
    ids = {int(x) for x in ids_raw.replace(";", ",").split(",") if x.strip().lstrip("-").isdigit()}
    return approval.Telegram(token, ids)


def cmd_demo(cfg, args) -> int:
    """Roda um episódio de demonstração ponta a ponta, sem internet e sem custo."""
    demo_cfg = load_config(overrides={
        "geral": {"workspace": "workspace-demo"},
        "video": {"largura": 640, "altura": 360, "fps": 15, "duracao_alvo_min": 1, "palavras_por_cena": 30},
        "imagens": {"provedor": "placeholder"}, "narracao": {"provedor": "silencio"},
    })
    pipe = Pipeline(demo_cfg, providers=[FakeProvider(__import__("vbp.demo", fromlist=["responder"]).responder)])
    pipe.state.add_episode("DEMO01", "Davi e Golias: a coragem que vem da confiança", "coragem e fé",
                           "1 Samuel 17:4-11; 1 Samuel 17:32-37; 1 Samuel 17:45-47", "Davi; Golias")
    s1 = pipe.run("DEMO01")
    last = s1["stages"][-1] if s1["stages"] else {}
    if last.get("stage") != "APROVACAO":
        print(f"\n1ª execução parou em {last.get('stage')}: {last.get('reason')}")
        return 1
    print(f"\n1ª execução: {s1['status']} — parou no gate humano, como esperado")
    approval.approve(pipe.state, "DEMO01", pipe.ep_dir("DEMO01"), "demo-automatica", "aprovação automática SÓ na demo")
    pipe2 = Pipeline(demo_cfg, providers=[FakeProvider(__import__("vbp.demo", fromlist=["responder"]).responder)])
    s2 = pipe2.run("DEMO01")
    print(f"2ª execução: {s2['status']} — vídeo em {pipe2.ep_dir('DEMO01') / 'video.mp4'}")
    return 0 if s2["status"] == "PASS" else 1


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="vbp", description=f"Video Bíblico Pipeline {__version__}")
    p.add_argument("--config", type=Path, help="caminho do TOML (padrão: config/pipeline.toml)")
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("init", help="cria config local, .env e workspace")
    sub.add_parser("doctor", help="health check do ambiente")
    a = sub.add_parser("add", help="adiciona um episódio à pauta")
    a.add_argument("id"); a.add_argument("--titulo", required=True); a.add_argument("--tema", required=True)
    a.add_argument("--referencias", required=True, help="separe por ';'"); a.add_argument("--personagens")
    i = sub.add_parser("import-pauta", help="importa episódios de um CSV (id,titulo,tema,referencias,personagens)")
    i.add_argument("csv")
    sub.add_parser("status", help="lista episódios, status e aprovação")
    r = sub.add_parser("run", help="executa o pipeline")
    r.add_argument("--episode", "-e"); r.add_argument("--until", help="para após esta etapa (ex.: STORYBOARD)")
    r.add_argument("--live", action="store_true", help="publica de verdade (exige aprovação); padrão é DRY_RUN")
    r.add_argument("--publicar-em", help="agendamento ISO 8601 UTC, ex.: 2026-12-01T21:00:00Z")
    r.add_argument("--fake-llm", action="store_true", help="usa o LLM de demonstração (sem custo)")
    ap = sub.add_parser("approve", help="aprova roteiro+storyboard (revisão humana)")
    ap.add_argument("id"); ap.add_argument("--por", required=True); ap.add_argument("--nota")
    rj = sub.add_parser("reject", help="pede ajuste; o próximo run refaz o roteiro com o motivo")
    rj.add_argument("id"); rj.add_argument("--motivo", required=True); rj.add_argument("--por", default="revisor")
    ex = sub.add_parser("explain", help="mostra por que cada decisão foi tomada")
    ex.add_argument("id"); ex.add_argument("--timeline", action="store_true")
    rp = sub.add_parser("report", help="métricas das últimas execuções")
    rp.add_argument("--ultimos", type=int, default=10)
    tr = sub.add_parser("telegram-review", help="envia resumo do episódio para revisão no Telegram")
    tr.add_argument("id")
    sub.add_parser("telegram-poll", help="processa /aprovar e /ajustar recebidos (uma passada)")
    sub.add_parser("demo", help="demonstração ponta a ponta sem internet")
    args = p.parse_args(argv)
    cfg = load_config(args.config)
    handlers = {"init": cmd_init, "doctor": cmd_doctor, "add": cmd_add, "import-pauta": cmd_import,
                "status": cmd_status, "run": cmd_run, "approve": cmd_approve, "reject": cmd_reject,
                "explain": cmd_explain, "report": cmd_report, "telegram-review": cmd_tg_review,
                "telegram-poll": cmd_tg_poll, "demo": cmd_demo}
    return handlers[args.cmd](cfg, args)


if __name__ == "__main__":
    raise SystemExit(main())
