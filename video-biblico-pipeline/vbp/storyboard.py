"""Etapa STORYBOARD: o "diretor" automático.

1. Divide a narração em cenas de ~N palavras (cada cena = 1 imagem).
2. Escolhe o enquadramento por REGRAS explícitas (palavra-gatilho → plano), com restrição de variedade
   (no máximo 2 planos iguais seguidos). Regras antes de LLM: custo zero e decisão explicável.
3. Aplica a ficha de personagens (consistência visual) e o estilo fixo ao prompt de imagem.
4. Opcional: LLM descreve a composição de cada cena (sem poder mudar o plano).
Cada decisão vai para storyboard.json.explain.json com a regra e a palavra que a dispararam.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

from .script import full_text, spoken_text

# Ordem = prioridade. (plano, motivo, palavras-gatilho)
SHOT_RULES: list[tuple[str, str, tuple[str, ...]]] = [
    ("dutch_angle", "conflito interior/instabilidade",
     ("atormentado", "angústia", "angustiado", "confusão", "tentação", "culpa", "loucura", "perturbado", "desespero")),
    ("low_angle", "poder/ameaça/autoridade",
     ("gigante", "rei", "exército", "poder", "trono", "ameaça", "faraó", "golias", "império", "soberano", "imponente")),
    ("high_angle", "vulnerabilidade/humildade",
     ("menino", "pequeno", "medo", "sozinho", "fraco", "humilde", "chorou", "ajoelhou", "prostrou", "frágil")),
    ("close_up", "detalhe decisivo/emoção",
     ("mão", "mãos", "pedra", "pedras", "olhos", "lágrima", "lágrimas", "carta", "espada", "pão", "cálice", "funda", "rosto")),
    ("pov", "perspectiva do personagem",
     ("viu", "olhou", "enxergou", "diante dele", "diante de si", "avistou", "contemplou")),
    ("birds_eye", "escala/visão geral",
     ("multidão", "nações", "terra inteira", "acampamento", "cidade inteira", "povo inteiro", "mar vermelho")),
    ("wide", "situar lugar/ambiente",
     ("vale", "deserto", "cidade", "mar", "monte", "montanha", "templo", "palácio", "campo", "rio", "jerusalém")),
]

SHOT_PROMPT = {
    "wide": "plano aberto mostrando o ambiente inteiro, personagem pequeno no quadro",
    "medium": "plano médio da cintura para cima",
    "close_up": "close-up detalhado",
    "low_angle": "câmera baixa olhando para cima, sujeito dominante e imponente",
    "high_angle": "câmera alta olhando para baixo, sujeito pequeno e vulnerável",
    "birds_eye": "vista aérea de cima, como um pássaro",
    "dutch_angle": "câmera inclinada (dutch angle), sensação de instabilidade",
    "pov": "ponto de vista em primeira pessoa do personagem",
}

# Movimento aplicado no render (Ken Burns) por plano.
SHOT_MOTION = {
    "wide": "pan_right", "medium": "zoom_in_slow", "close_up": "zoom_in", "low_angle": "tilt_up",
    "high_angle": "zoom_out", "birds_eye": "zoom_out_slow", "dutch_angle": "zoom_in_slow", "pov": "zoom_in",
}


def split_scenes(script: dict, words_per_scene: int) -> list[dict]:
    """Quebra por frases, agrupando até ~words_per_scene palavras. Preserva a seção de origem."""
    blocks = [("gancho", script.get("gancho", ""))]
    blocks += [(f"secao_{i}", s.get("texto", "")) for i, s in enumerate(script.get("secoes", []), 1)]
    blocks.append(("conclusao", script.get("conclusao", "")))
    scenes: list[dict] = []
    for origin, text in blocks:
        sentences = [s.strip() for s in re.split(r"(?<=[.!?])\s+", text.strip()) if s.strip()]
        buf: list[str] = []
        for sent in sentences:
            buf.append(sent)
            if len(" ".join(buf).split()) >= words_per_scene:
                scenes.append({"origem": origin, "texto": " ".join(buf)})
                buf = []
        if buf:
            scenes.append({"origem": origin, "texto": " ".join(buf)})
    for i, sc in enumerate(scenes, 1):
        sc["id"] = i
        sc["texto"], sc["referencias"] = spoken_text(sc["texto"])  # narração/legenda sem "(1 Samuel 17:45)"
    return scenes


def _match(text: str, words: tuple[str, ...]) -> str | None:
    low = text.lower()
    for w in words:
        if re.search(rf"(?<!\w){re.escape(w)}(?!\w)", low):
            return w
    return None


def choose_shot(text: str, previous: list[str], is_section_start: bool) -> dict:
    candidates = []
    for shot, reason, words in SHOT_RULES:
        hit = _match(text, words)
        if hit:
            candidates.append({"shot": shot, "rule": reason, "matched": hit})
    if is_section_start and not any(c["shot"] == "wide" for c in candidates[:1]):
        place = next((c for c in candidates if c["shot"] == "wide"), None)
        if place:  # início de seção com lugar citado: situar o espectador primeiro
            candidates.insert(0, {**place, "rule": "início de seção + lugar citado"})
    candidates.append({"shot": "medium", "rule": "padrão (nenhum gatilho)", "matched": None})
    for cand in candidates:  # restrição de variedade: no máximo 2 iguais seguidos
        if previous[-2:] != [cand["shot"], cand["shot"]]:
            return cand
    alt = "wide" if previous[-1:] != ["wide"] else "medium"
    return {"shot": alt, "rule": "variedade (evitar 3 planos iguais seguidos)", "matched": None}


def characters_in(text: str, cfg) -> list[dict]:
    found = []
    for key, ch in (cfg.get_path("personagens", {}) or {}).items():
        names = ch.get("nomes", [key])
        if any(re.search(rf"(?<!\w){re.escape(n)}(?!\w)", text) for n in names):
            found.append({"id": key, "descricao": ch.get("descricao", ""), "seed": ch.get("seed")})
    return found


def build_storyboard(script: dict, cfg) -> tuple[dict, dict]:
    scenes = split_scenes(script, int(cfg.get_path("video.palavras_por_cena", 55)))
    style = cfg.get_path("imagens.estilo", "")
    history: list[str] = []
    decisions = []
    last_origin = None
    for sc in scenes:
        choice = choose_shot(sc["texto"], history, sc["origem"] != last_origin)
        last_origin = sc["origem"]
        history.append(choice["shot"])
        chars = characters_in(sc["texto"], cfg)
        sc.update({
            "plano": choice["shot"], "movimento": SHOT_MOTION[choice["shot"]], "personagens": chars,
            "seed": chars[0]["seed"] if chars and chars[0].get("seed") is not None else 1000 + sc["id"],
            "descricao": sc["texto"][:220],
        })
        decisions.append({"cena": sc["id"], "plano": choice["shot"], "regra": choice["rule"],
                          "gatilho": choice["matched"], "personagens": [c["id"] for c in chars]})
    for sc in scenes:
        sc["prompt_imagem"] = image_prompt(sc, style)
    board = {"titulo": script.get("titulo"), "texto_thumbnail": script.get("texto_thumbnail"),
             "estilo": style, "cenas": scenes}
    explain = {"metodo": "regras determinísticas (vbp/storyboard.py::SHOT_RULES)",
               "total_cenas": len(scenes), "distribuicao_planos": _dist(history), "decisoes": decisions}
    return board, explain


def image_prompt(scene: dict, style: str) -> str:
    chars = "; ".join(f"{c['id']}: {c['descricao']}" for c in scene.get("personagens", []))
    parts = [SHOT_PROMPT[scene["plano"]], scene.get("descricao", ""), chars, style]
    return ". ".join(p for p in parts if p)


def apply_llm_descriptions(board: dict, descriptions: dict, style: str) -> int:
    """Aplica descrições do LLM sem permitir troca de plano. Retorna quantas cenas foram atualizadas."""
    by_id = {int(d.get("id")): str(d.get("descricao", "")).strip()
             for d in descriptions.get("cenas", []) if str(d.get("id", "")).isdigit() or isinstance(d.get("id"), int)}
    n = 0
    for sc in board["cenas"]:
        desc = by_id.get(sc["id"])
        if desc:
            sc["descricao"] = " ".join(desc.split()[:40])
            sc["prompt_imagem"] = image_prompt(sc, style)
            n += 1
    return n


def storyboard_prompt(board: dict, cfg, root: Path) -> str:
    from .script import render_template
    tpl = (root / "prompts" / "storyboard.md").read_text(encoding="utf-8")
    chars = json.dumps(cfg.get_path("personagens", {}), ensure_ascii=False)
    cenas = "\n".join(f"{s['id']} | {s['plano']} | {s['texto']}" for s in board["cenas"])
    return render_template(tpl, {"PERSONAGENS": chars, "CENAS": cenas})


def _dist(shots: list[str]) -> dict:
    out: dict[str, int] = {}
    for s in shots:
        out[s] = out.get(s, 0) + 1
    return out


def total_words(script: dict) -> int:
    return len(full_text(script).split())
