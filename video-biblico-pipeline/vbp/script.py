"""Etapa ROTEIRO: gera o roteiro via LLM e valida de forma determinística.

Fluxo limitado: gera → valida → (se falhar) regenera com o feedback dos erros, até
max_tentativas_por_etapa. Depois disso, BLOCKED com diagnóstico — nada de loop infinito.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

from .bible_refs import find_refs, parse_ref
from .config import ROOT

BANNED = [
    "não pule", "nao pule", "deus mandou essa mensagem", "deus te mandou", "compartilhe ou",
    "o que a igreja esconde", "a igreja esconde", "segredo proibido", "o que não querem que você saiba",
    "querem esconder", "verdade oculta", "você foi escolhido para ver", "[corta", "[corte", "(cena:",
]


def render_template(template: str, values: dict[str, str]) -> str:
    out = template
    for key, val in values.items():
        out = out.replace("{" + key + "}", str(val))
    return out


def word_count(text: str) -> int:
    return len(re.findall(r"\b\w+\b", text, re.UNICODE))


def spoken_text(text: str) -> tuple[str, list[str]]:
    """Remove '(Livro cap:vers)' da fala/legenda e devolve as referências separadas.

    Referência lida em voz alta quebra o ritmo; ela vai para a descrição do vídeo (ADR-008).
    """
    refs = find_refs(text)
    clean = text
    for r in refs:
        clean = clean.replace(f"({r})", "")
    clean = re.sub(r"\s+([.,;:!?])", r"\1", re.sub(r"\s{2,}", " ", clean)).strip()
    return clean, refs


def full_text(script: dict) -> str:
    parts = [script.get("gancho", "")]
    parts += [s.get("texto", "") for s in script.get("secoes", [])]
    parts.append(script.get("conclusao", ""))
    return "\n\n".join(p for p in parts if p)


def target_words(cfg) -> int:
    return int(cfg.get_path("video.duracao_alvo_min", 20) * cfg.get_path("video.palavras_por_minuto", 140))


def validate_script(script: dict, cfg) -> list[dict]:
    """Lista de checks {check, status, detail}. Determinístico e explicável."""
    checks: list[dict] = []

    def add(name: str, ok: bool, detail: str = "") -> None:
        checks.append({"check": name, "status": "PASS" if ok else "FAIL", "detail": detail})

    if not isinstance(script, dict):
        add("formato_json", False, "resposta não é um objeto JSON")
        return checks
    required = ["titulo", "texto_thumbnail", "gancho", "secoes", "conclusao", "descricao_youtube"]
    missing = [k for k in required if not script.get(k)]
    add("campos_obrigatorios", not missing, f"faltando: {missing}" if missing else "")
    secoes = script.get("secoes") or []
    smin, smax = cfg.get_path("roteiro.secoes_min", 6), cfg.get_path("roteiro.secoes_max", 8)
    add("quantidade_secoes", smin <= len(secoes) <= smax, f"{len(secoes)} seções (esperado {smin}–{smax})")
    add("titulo_tamanho", 0 < len(str(script.get("titulo", ""))) <= 70, f"{len(str(script.get('titulo', '')))} caracteres")
    thumb_words = len(str(script.get("texto_thumbnail", "")).split())
    add("thumbnail_2a3_palavras", 1 <= thumb_words <= 3, f"{thumb_words} palavra(s)")

    invalid_refs, sections_without_ref = [], []
    for i, sec in enumerate(secoes, 1):
        refs = find_refs(str(sec.get("texto", "")))
        if not refs:
            sections_without_ref.append(i)
        for r in refs:
            ref, why = parse_ref(r)
            if not ref:
                invalid_refs.append(f"seção {i}: {why}")
    add("referencia_por_secao", not sections_without_ref,
        f"seções sem referência: {sections_without_ref}" if sections_without_ref else "")
    add("referencias_validas", not invalid_refs, "; ".join(invalid_refs))

    text = full_text(script).lower()
    hits = [b for b in BANNED if b in text]
    add("sem_isca_ou_direcao_de_cena", not hits, f"encontrado: {hits}" if hits else "")

    words, target = word_count(full_text(script)), target_words(cfg)
    tol = float(cfg.get_path("roteiro.tolerancia_palavras", 0.35))
    lo, hi = int(target * (1 - tol)), int(target * (1 + tol))
    add("duracao_estimada", lo <= words <= hi, f"{words} palavras (alvo {target}, aceito {lo}–{hi})")
    return checks


def failed(checks: list[dict]) -> list[dict]:
    return [c for c in checks if c["status"] == "FAIL"]


def build_prompt(episode: dict, cfg, feedback: str = "") -> str:
    tpl = (ROOT / "prompts" / "roteiro.md").read_text(encoding="utf-8")
    editorial = (ROOT / "prompts" / "editorial.md").read_text(encoding="utf-8")
    dados = json.dumps({k: episode[k] for k in ("id", "titulo", "tema", "referencias", "personagens")},
                       ensure_ascii=False, indent=2)
    fb = ""
    if feedback:
        fb = "\n=== CORRIJA OS PROBLEMAS DA VERSÃO ANTERIOR ===\n" + feedback
    return render_template(tpl, {
        "DURACAO_MIN": cfg.get_path("video.duracao_alvo_min", 20), "PALAVRAS_ALVO": target_words(cfg),
        "EDITORIAL": editorial, "DADOS": dados, "SECOES_MIN": cfg.get_path("roteiro.secoes_min", 6),
        "SECOES_MAX": cfg.get_path("roteiro.secoes_max", 8), "FEEDBACK": fb,
    })


def to_markdown(script: dict) -> str:
    lines = [f"# {script['titulo']}", "", f"**Thumbnail:** {script['texto_thumbnail']}", "",
             "## Gancho", "", script["gancho"], ""]
    for i, s in enumerate(script["secoes"], 1):
        lines += [f"## {i}. {s.get('titulo', '')}", "", s["texto"], ""]
    lines += ["## Conclusão", "", script["conclusao"], "", "## Descrição do YouTube", "", script["descricao_youtube"]]
    return "\n".join(lines)


def save_script(ep_dir: Path, script: dict) -> Path:
    ep_dir.mkdir(parents=True, exist_ok=True)
    path = ep_dir / "roteiro.json"
    path.write_text(json.dumps(script, ensure_ascii=False, indent=2), encoding="utf-8")
    (ep_dir / "roteiro.md").write_text(to_markdown(script), encoding="utf-8")
    return path
