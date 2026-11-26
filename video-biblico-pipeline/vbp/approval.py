"""Gate de aprovação humana (revisão teológica).

A aprovação vale para um conteúdo específico: grava o SHA-256 de roteiro+storyboard.
Se qualquer um mudar depois, a aprovação deixa de valer e o episódio volta a AGUARDANDO_APROVACAO.
Canais: CLI (padrão) ou Telegram (lista de chat IDs autorizados; padrão reaproveitado do Fitness Manager).
"""
from __future__ import annotations

import json
import urllib.request
from pathlib import Path

from .state import State, sha256_text


def content_hash(ep_dir: Path) -> str:
    parts = []
    for name in ("roteiro.json", "storyboard.json"):
        p = ep_dir / name
        parts.append(p.read_text(encoding="utf-8") if p.exists() else "")
    return sha256_text(*parts)


def is_approved(state: State, ep_id: str, ep_dir: Path) -> tuple[bool, str]:
    last = state.latest_approval(ep_id)
    if not last:
        return False, "nenhuma aprovação registrada"
    if last["decision"] != "APROVADO":
        return False, f"ajuste solicitado: {last.get('note') or '-'}"
    if last["content_hash"] != content_hash(ep_dir):
        return False, "conteúdo mudou depois da aprovação (hash diferente) — revisar de novo"
    return True, f"aprovado por {last['approver']} em {last['ts']}"


def approve(state: State, ep_id: str, ep_dir: Path, approver: str, note: str = "") -> str:
    if not (ep_dir / "roteiro.json").exists() or not (ep_dir / "storyboard.json").exists():
        raise ValueError("roteiro/storyboard ainda não existem para este episódio")
    h = content_hash(ep_dir)
    state.record_approval(ep_id, "APROVADO", approver, h, note)
    state.set_status(ep_id, "APROVADO")
    return h


def request_changes(state: State, ep_id: str, ep_dir: Path, approver: str, reason: str) -> None:
    state.record_approval(ep_id, "AJUSTE_SOLICITADO", approver, content_hash(ep_dir), reason)
    state.set_status(ep_id, "AJUSTE_SOLICITADO")


def review_summary(ep_id: str, ep_dir: Path, max_chars: int = 3800) -> str:
    script = json.loads((ep_dir / "roteiro.json").read_text(encoding="utf-8"))
    board = json.loads((ep_dir / "storyboard.json").read_text(encoding="utf-8"))
    dist: dict[str, int] = {}
    for s in board["cenas"]:
        dist[s["plano"]] = dist.get(s["plano"], 0) + 1
    lines = [f"Revisão {ep_id}: {script['titulo']}", f"Thumb: {script['texto_thumbnail']}", "",
             "Seções:"] + [f"{i}. {s.get('titulo', '')}" for i, s in enumerate(script["secoes"], 1)]
    lines += ["", f"Cenas: {len(board['cenas'])} | Planos: {dist}", "",
              f"Responda /aprovar {ep_id}  ou  /ajustar {ep_id} <motivo>",
              f"Roteiro completo: {ep_dir / 'roteiro.md'}"]
    return "\n".join(lines)[:max_chars]


class Telegram:
    def __init__(self, token: str, allowed_chat_ids: set[int]):
        if not token or not allowed_chat_ids:
            raise ValueError("Telegram exige token e ao menos um chat ID autorizado (variáveis de ambiente)")
        self.base = f"https://api.telegram.org/bot{token}/"
        self.allowed = allowed_chat_ids

    def _call(self, method: str, payload: dict) -> dict:
        req = urllib.request.Request(self.base + method, data=json.dumps(payload).encode(),
                                     headers={"Content-Type": "application/json"}, method="POST")
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read().decode())
        if not data.get("ok"):
            raise RuntimeError(f"Telegram recusou {method}")
        return data

    def send(self, text: str) -> None:
        for chat in self.allowed:
            self._call("sendMessage", {"chat_id": chat, "text": text[:4000]})

    def poll_once(self, state: State, workspace: Path) -> list[str]:
        """Processa comandos pendentes UMA vez (sem daemon). Offset persistido → idempotente."""
        offset = int(state.kv_get("telegram_offset", 0))
        updates = self._call("getUpdates", {"offset": offset, "timeout": 0}).get("result", [])
        handled = []
        for upd in updates:
            state.kv_set("telegram_offset", int(upd["update_id"]) + 1)
            msg = upd.get("message") or {}
            chat = (msg.get("chat") or {}).get("id")
            text = (msg.get("text") or "").strip()
            if chat not in self.allowed or not text.startswith("/"):
                continue  # remetente não autorizado: ignorado
            parts = text.split(maxsplit=2)
            cmd, ep_id = parts[0].lower(), (parts[1].upper() if len(parts) > 1 else "")
            ep_dir = workspace / "episodios" / ep_id
            who = f"telegram:{chat}"
            if cmd == "/aprovar" and ep_id:
                approve(state, ep_id, ep_dir, who)
                handled.append(f"{ep_id} aprovado")
            elif cmd == "/ajustar" and ep_id:
                request_changes(state, ep_id, ep_dir, who, parts[2] if len(parts) > 2 else "sem motivo")
                handled.append(f"{ep_id} ajuste solicitado")
        return handled
