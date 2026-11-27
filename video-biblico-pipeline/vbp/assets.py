"""Controle dos arquivos de mídia por cena: validade (cache) e registro de licença.

Validade: o nome `cena_NNN` não diz de qual texto o arquivo veio. O manifesto guarda, por cena, o hash da
entrada e o hash do arquivo. Mudou a entrada e o arquivo continua o mesmo → está velho: vai para `_antigos/`
(nunca é apagado). Arquivo trocado por uma pessoa → é aceito como a nova versão.

Licença: todo arquivo que NÃO foi gerado pelo pipeline precisa de uma linha em `licencas.csv`.
"""
from __future__ import annotations

import csv
import json
import re
import shutil
from pathlib import Path

from .state import sha256_file

LICENSE_FILE = "licencas.csv"
LICENSE_FIELDS = ("arquivo", "autor", "licenca", "origem")
FORBIDDEN = re.compile(r"(?<![a-z])(nc|nd)(?![a-z])|n[ãa]o[ -]comercial|sem deriva", re.I)


class Manifest:
    def __init__(self, folder: Path):
        self.folder = folder
        self.path = folder / "manifesto.json"
        self.data: dict = json.loads(self.path.read_text(encoding="utf-8")) if self.path.exists() else {}

    def reusable(self, stem: str, found: Path, input_hash: str) -> bool:
        """True se o arquivo existente serve para a entrada atual; se estiver velho, arquiva e devolve False."""
        entry = self.data.get(stem)
        file_hash = sha256_file(found)
        if entry and entry["arquivo_hash"] == file_hash:
            if entry["entrada"] == input_hash:
                return True
            self._archive(found)
            del self.data[stem]
            self.save()
            return False
        # arquivo novo ou trocado por uma pessoa (também cobre workspaces criados antes do manifesto)
        self.record(stem, found, input_hash, generated=False)
        return True

    def record(self, stem: str, path: Path, input_hash: str, generated: bool) -> None:
        self.data[stem] = {"arquivo": path.name, "entrada": input_hash, "arquivo_hash": sha256_file(path),
                           "gerado": generated}
        self.save()

    def save(self) -> None:
        self.path.write_text(json.dumps(self.data, ensure_ascii=False, indent=2), encoding="utf-8")

    def _archive(self, path: Path) -> None:
        old = self.folder / "_antigos"
        old.mkdir(exist_ok=True)
        target, n = old / path.name, 1
        while target.exists():
            target, n = old / f"{path.stem}.{n}{path.suffix}", n + 1
        shutil.move(str(path), str(target))


def external_files(ep_dir: Path) -> list[str]:
    """Caminhos relativos (ex.: imagens/cena_001.png) dos arquivos fornecidos por uma pessoa."""
    out = []
    for sub in ("imagens", "audio"):
        data = Manifest(ep_dir / sub).data if (ep_dir / sub).is_dir() else {}
        out += [f"{sub}/{e['arquivo']}" for e in data.values() if not e["gerado"]]
    return sorted(out)


def read_licenses(ep_dir: Path) -> list[dict]:
    path = ep_dir / LICENSE_FILE
    if not path.exists():
        return []
    with path.open(encoding="utf-8-sig", newline="") as fh:
        return [{k: (row.get(k) or "").strip() for k in LICENSE_FIELDS} for row in csv.DictReader(fh)]


def check_licenses(ep_dir: Path) -> tuple[list[str], list[str]]:
    """(problemas, créditos). `arquivo` aceita nome exato ou curinga, ex.: audio/*."""
    rows = read_licenses(ep_dir)
    problems, credits = [], []
    for name in external_files(ep_dir):
        row = next((r for r in rows if r["arquivo"] == name), None) or next(
            (r for r in rows if r["arquivo"].endswith("/*") and name.startswith(r["arquivo"][:-1])), None)
        if not row or not row["autor"] or not row["licenca"]:
            problems.append(f"{name}: sem autor/licença em {LICENSE_FILE}")
            continue
        if FORBIDDEN.search(row["licenca"]):
            problems.append(f"{name}: licença '{row['licenca']}' proíbe uso comercial ou obra derivada")
            continue
        credit = f"{row['autor']} ({row['licenca']})" + (f" {row['origem']}" if row["origem"] else "")
        if credit not in credits:
            credits.append(credit)
    return problems, credits
