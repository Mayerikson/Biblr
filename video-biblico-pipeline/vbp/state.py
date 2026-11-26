"""Estado do pipeline em SQLite (fonte de verdade; o chat/IA não é).

- episodes: um registro por episódio, com status atual.
- events: histórico append-only (nunca UPDATE/DELETE) — auditoria e linha do tempo.
- artifacts: hash das entradas de cada etapa → idempotência (etapa não refaz trabalho igual)
  e invalidação automática (mudou o roteiro? a aprovação anterior deixa de valer).
- llm_cache: respostas de LLM por hash do prompt → não pagar duas vezes pela mesma coisa.
- kv: offsets do Telegram e afins.
"""
from __future__ import annotations

import hashlib
import json
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

from .obs import now_iso

# Ordem do fluxo. AJUSTE_SOLICITADO e BLOQUEADO são estados laterais.
STAGES = ["PAUTA", "ROTEIRO", "STORYBOARD", "AGUARDANDO_APROVACAO", "APROVADO",
          "IMAGENS", "NARRACAO", "RENDER", "PRONTO", "PUBLICADO"]

SCHEMA = """
PRAGMA journal_mode=WAL;
PRAGMA foreign_keys=ON;
CREATE TABLE IF NOT EXISTS episodes (
  id TEXT PRIMARY KEY,
  titulo TEXT NOT NULL,
  tema TEXT NOT NULL,
  referencias TEXT NOT NULL,
  personagens TEXT NOT NULL DEFAULT '',
  status TEXT NOT NULL DEFAULT 'PAUTA',
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS events (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  ts TEXT NOT NULL,
  run_id TEXT,
  episode_id TEXT,
  stage TEXT,
  event TEXT NOT NULL,
  status TEXT,
  data TEXT
);
CREATE TRIGGER IF NOT EXISTS events_no_update BEFORE UPDATE ON events
BEGIN SELECT RAISE(ABORT, 'events e append-only'); END;
CREATE TRIGGER IF NOT EXISTS events_no_delete BEFORE DELETE ON events
BEGIN SELECT RAISE(ABORT, 'events e append-only'); END;
CREATE TABLE IF NOT EXISTS artifacts (
  episode_id TEXT NOT NULL,
  stage TEXT NOT NULL,
  path TEXT NOT NULL,
  input_hash TEXT NOT NULL,
  created_at TEXT NOT NULL,
  PRIMARY KEY (episode_id, stage)
);
CREATE TABLE IF NOT EXISTS approvals (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  episode_id TEXT NOT NULL,
  decision TEXT NOT NULL CHECK (decision IN ('APROVADO','AJUSTE_SOLICITADO')),
  approver TEXT NOT NULL,
  content_hash TEXT NOT NULL,
  note TEXT,
  ts TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS llm_cache (
  key TEXT PRIMARY KEY,
  provider TEXT NOT NULL,
  model TEXT NOT NULL,
  response TEXT NOT NULL,
  created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS kv (k TEXT PRIMARY KEY, v TEXT NOT NULL);
"""


def sha256_text(*parts: str) -> str:
    h = hashlib.sha256()
    for p in parts:
        h.update(p.encode("utf-8"))
        h.update(b"\x00")
    return h.hexdigest()


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with Path(path).open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 16), b""):
            h.update(chunk)
    return h.hexdigest()


class State:
    def __init__(self, db_path: Path):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with self.conn() as c:
            c.executescript(SCHEMA)

    @contextmanager
    def conn(self) -> Iterator[sqlite3.Connection]:
        c = sqlite3.connect(self.db_path)
        c.row_factory = sqlite3.Row
        try:
            yield c
            c.commit()
        finally:
            c.close()

    # ---- episódios -----------------------------------------------------
    def add_episode(self, ep_id: str, titulo: str, tema: str, referencias: str, personagens: str = "") -> bool:
        """Idempotente: o mesmo ID não é inserido duas vezes. Retorna True se inseriu."""
        ts = now_iso()
        with self.conn() as c:
            cur = c.execute(
                "INSERT OR IGNORE INTO episodes(id,titulo,tema,referencias,personagens,status,created_at,updated_at)"
                " VALUES (?,?,?,?,?,'PAUTA',?,?)", (ep_id, titulo, tema, referencias, personagens, ts, ts))
            return cur.rowcount == 1

    def episode(self, ep_id: str) -> dict | None:
        with self.conn() as c:
            row = c.execute("SELECT * FROM episodes WHERE id=?", (ep_id,)).fetchone()
        return dict(row) if row else None

    def episodes(self) -> list[dict]:
        with self.conn() as c:
            return [dict(r) for r in c.execute("SELECT * FROM episodes ORDER BY id")]

    def set_status(self, ep_id: str, status: str) -> None:
        with self.conn() as c:
            c.execute("UPDATE episodes SET status=?, updated_at=? WHERE id=?", (status, now_iso(), ep_id))

    # ---- eventos (sink do Observer) -----------------------------------
    def append_event(self, record: dict) -> None:
        with self.conn() as c:
            c.execute(
                "INSERT INTO events(ts,run_id,episode_id,stage,event,status,data) VALUES (?,?,?,?,?,?,?)",
                (record.get("ts"), record.get("run_id"), record.get("episode"), record.get("stage"),
                 record.get("event"), record.get("status"), json.dumps(record.get("data", {}), ensure_ascii=False)))

    def timeline(self, ep_id: str, limit: int = 200) -> list[dict]:
        with self.conn() as c:
            rows = c.execute("SELECT * FROM events WHERE episode_id=? ORDER BY id DESC LIMIT ?", (ep_id, limit))
            return [dict(r) for r in rows][::-1]

    # ---- artefatos / idempotência -------------------------------------
    def artifact(self, ep_id: str, stage: str) -> dict | None:
        with self.conn() as c:
            row = c.execute("SELECT * FROM artifacts WHERE episode_id=? AND stage=?", (ep_id, stage)).fetchone()
        return dict(row) if row else None

    def save_artifact(self, ep_id: str, stage: str, path: Path, input_hash: str) -> None:
        with self.conn() as c:
            c.execute(
                "INSERT INTO artifacts(episode_id,stage,path,input_hash,created_at) VALUES (?,?,?,?,?)"
                " ON CONFLICT(episode_id,stage) DO UPDATE SET path=excluded.path,"
                " input_hash=excluded.input_hash, created_at=excluded.created_at",
                (ep_id, stage, str(path), input_hash, now_iso()))

    def is_fresh(self, ep_id: str, stage: str, input_hash: str) -> bool:
        art = self.artifact(ep_id, stage)
        return bool(art and art["input_hash"] == input_hash and Path(art["path"]).exists())

    # ---- aprovação humana ---------------------------------------------
    def record_approval(self, ep_id: str, decision: str, approver: str, content_hash: str, note: str = "") -> None:
        with self.conn() as c:
            c.execute("INSERT INTO approvals(episode_id,decision,approver,content_hash,note,ts) VALUES (?,?,?,?,?,?)",
                      (ep_id, decision, approver, content_hash, note, now_iso()))

    def latest_approval(self, ep_id: str) -> dict | None:
        with self.conn() as c:
            row = c.execute("SELECT * FROM approvals WHERE episode_id=? ORDER BY id DESC LIMIT 1", (ep_id,)).fetchone()
        return dict(row) if row else None

    # ---- cache de LLM --------------------------------------------------
    def cache_get(self, key: str) -> str | None:
        with self.conn() as c:
            row = c.execute("SELECT response FROM llm_cache WHERE key=?", (key,)).fetchone()
        return row["response"] if row else None

    def cache_put(self, key: str, provider: str, model: str, response: str) -> None:
        with self.conn() as c:
            c.execute("INSERT OR REPLACE INTO llm_cache(key,provider,model,response,created_at) VALUES (?,?,?,?,?)",
                      (key, provider, model, response, now_iso()))

    # ---- kv ------------------------------------------------------------
    def kv_get(self, k: str, default: Any = None) -> Any:
        with self.conn() as c:
            row = c.execute("SELECT v FROM kv WHERE k=?", (k,)).fetchone()
        return json.loads(row["v"]) if row else default

    def kv_set(self, k: str, v: Any) -> None:
        with self.conn() as c:
            c.execute("INSERT OR REPLACE INTO kv(k,v) VALUES (?,?)", (k, json.dumps(v)))
