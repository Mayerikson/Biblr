"""Etapa PUBLICACAO (YouTube Data API v3).

- DRY_RUN (padrão): só grava publish_plan.json com os metadados — nada sai da máquina.
- LIVE: exige --live na CLI, aprovação válida e envia SEMPRE como 'private' (ou agendado com publishAt).
  O agendamento usa o próprio YouTube: não precisamos de servidor/cron (ver ADR-006).
- Dependências opcionais: google-api-python-client, google-auth-oauthlib (requirements-optional.txt).
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from .assets import check_licenses
from .obs import StageResult


def normalize_publish_at(value: str) -> str:
    """Valida o agendamento: ISO 8601 com fuso, no futuro. Devolve em UTC."""
    try:
        when = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError as exc:
        raise StageResult("BLOCKED", f"--publicar-em inválido: '{value}' (ex.: 2027-01-05T21:00:00Z)") from exc
    if when.tzinfo is None:
        raise StageResult("BLOCKED", "--publicar-em precisa de fuso (termine com Z ou -03:00)")
    if when <= datetime.now(timezone.utc):
        raise StageResult("BLOCKED", f"--publicar-em está no passado: {value}")
    return when.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def build_description(ep_dir: Path, text: str, credits: list[str]) -> str:
    """Descrição + referências e créditos montados por código (não dependem do LLM). Limite de 4900."""
    extra = ""
    board_path = ep_dir / "storyboard.json"
    if board_path.exists():
        board = json.loads(board_path.read_text(encoding="utf-8"))
        refs = list(dict.fromkeys(r for s in board["cenas"] for r in s.get("referencias", [])))
        if refs:
            extra += "\n\nReferências bíblicas: " + "; ".join(refs)
    if credits:
        extra += "\n\nCréditos:\n" + "\n".join(f"- {c}" for c in credits)
    # o texto do LLM é cortado antes; referências e créditos são preservados
    full = text[:max(0, 4900 - len(extra))] + extra
    return full.replace("<", "‹").replace(">", "›")[:4900]


def build_metadata(ep_dir: Path, cfg, publish_at: str | None = None) -> dict:
    script = json.loads((ep_dir / "roteiro.json").read_text(encoding="utf-8"))
    _, credits = check_licenses(ep_dir)
    status = {"privacyStatus": cfg.get_path("publicacao.privacidade", "private"), "selfDeclaredMadeForKids": False,
              "containsSyntheticMedia": True}  # transparência: conteúdo com imagens/voz geradas por IA
    if publish_at:
        status["privacyStatus"] = "private"
        status["publishAt"] = normalize_publish_at(publish_at)
    return {
        "snippet": {"title": script["titulo"][:100], "description": build_description(ep_dir, script["descricao_youtube"], credits),
                    "categoryId": str(cfg.get_path("publicacao.categoria_id", "27")),
                    "defaultLanguage": "pt-BR", "defaultAudioLanguage": "pt-BR"},
        "status": status,
    }


def publish(ep_dir: Path, cfg, live: bool, publish_at: str | None = None,
            on_uploaded: Callable[[str], None] | None = None) -> dict:
    meta = build_metadata(ep_dir, cfg, publish_at)
    plan = {"modo": "LIVE" if live else "DRY_RUN", "video": str(ep_dir / "video.mp4"),
            "thumbnail": str(ep_dir / "thumbnail.png"), "legendas": str(ep_dir / "legendas.srt"), "metadata": meta,
            "pendencias_licenca": check_licenses(ep_dir)[0]}
    (ep_dir / "publish_plan.json").write_text(json.dumps(plan, ensure_ascii=False, indent=2), encoding="utf-8")
    if not live:
        return {**plan, "video_id": None}
    if plan["pendencias_licenca"]:
        raise StageResult("BLOCKED", "licenças pendentes: " + "; ".join(plan["pendencias_licenca"][:3]))
    try:
        from google.oauth2.credentials import Credentials
        from google_auth_oauthlib.flow import InstalledAppFlow
        from googleapiclient.discovery import build
        from googleapiclient.http import MediaFileUpload
    except ImportError as exc:
        raise StageResult("BLOCKED", "instale requirements-optional.txt para publicar no YouTube") from exc
    scopes = ["https://www.googleapis.com/auth/youtube.upload", "https://www.googleapis.com/auth/youtube.force-ssl"]
    from .config import ROOT
    token_path = Path(cfg.get_path("publicacao.token_path"))
    token_path = token_path if token_path.is_absolute() else ROOT / token_path
    if token_path.exists():
        creds = Credentials.from_authorized_user_file(str(token_path), scopes)
    else:
        secret = Path(cfg.get_path("publicacao.client_secret"))
        secret = secret if secret.is_absolute() else ROOT / secret
        if not secret.exists():
            raise StageResult("BLOCKED", f"client_secret do Google não encontrado em {secret}")
        creds = InstalledAppFlow.from_client_secrets_file(str(secret), scopes).run_local_server(port=0)
        token_path.parent.mkdir(parents=True, exist_ok=True)
        token_path.write_text(creds.to_json(), encoding="utf-8")
    yt = build("youtube", "v3", credentials=creds)
    req = yt.videos().insert(part="snippet,status", body=meta,
                             media_body=MediaFileUpload(str(ep_dir / "video.mp4"), chunksize=-1, resumable=True))
    resp = None
    while resp is None:
        _, resp = req.next_chunk()
    vid = resp["id"]
    if on_uploaded:  # registra ANTES de thumbnail/legenda: se falharem, o vídeo não é enviado de novo
        on_uploaded(vid)
    if (ep_dir / "thumbnail.png").exists():
        yt.thumbnails().set(videoId=vid, media_body=MediaFileUpload(str(ep_dir / "thumbnail.png"))).execute()
    if (ep_dir / "legendas.srt").exists():
        yt.captions().insert(part="snippet", body={"snippet": {"videoId": vid, "language": "pt-BR", "name": "Português"}},
                             media_body=MediaFileUpload(str(ep_dir / "legendas.srt"))).execute()
    plan["video_id"] = vid
    (ep_dir / "publish_plan.json").write_text(json.dumps(plan, ensure_ascii=False, indent=2), encoding="utf-8")
    return plan
