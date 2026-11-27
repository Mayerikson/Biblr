"""Etapas IMAGENS, NARRACAO e RENDER (ffmpeg), legendas e thumbnail.

Provedores plugáveis, todos locais por padrão:
- imagens: placeholder (teste), externo (você gera em qualquer ferramenta e solta os arquivos), a1111 (API do
  Automatic1111/Forge rodando na sua máquina).
- narração: silencio (teste/tempo), externo (seus arquivos de áudio), piper (TTS local, se instalado),
  edge (pacote edge-tts; o texto é enviado a um serviço online — leia os termos antes de monetizar).
Cada cena tem SEU áudio → o vídeo e as legendas ficam sincronizados por construção.
"""
from __future__ import annotations

import base64
import json
import math
import re
import shutil
import subprocess
import urllib.request
from pathlib import Path

from .assets import Manifest
from .obs import StageResult
from .state import sha256_file, sha256_text

IMG_EXT = (".png", ".jpg", ".jpeg", ".webp")
AUD_EXT = (".wav", ".mp3", ".m4a", ".ogg")


def require_ffmpeg() -> None:
    if not shutil.which("ffmpeg") or not shutil.which("ffprobe"):
        raise StageResult("BLOCKED", "ffmpeg/ffprobe não encontrados no PATH (veja README > Requisitos)")


def run(cmd: list[str]) -> None:
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        tail = (proc.stderr or "")[-600:]
        raise RuntimeError(f"comando falhou ({cmd[0]}): {tail}")


def probe_duration(path: Path) -> float:
    out = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of",
                          "default=noprint_wrappers=1:nokey=1", str(path)], capture_output=True, text=True)
    try:
        return float(out.stdout.strip())
    except ValueError as exc:
        raise RuntimeError(f"não consegui medir a duração de {path.name}") from exc


def scene_name(scene_id: int) -> str:
    return f"cena_{scene_id:03d}"


def _find(folder: Path, stem: str, exts: tuple[str, ...]) -> Path | None:
    for ext in exts:
        p = folder / f"{stem}{ext}"
        if p.exists():
            return p
    return None


# ------------------------------------------------------------------ imagens
def make_images(board: dict, ep_dir: Path, cfg) -> dict:
    folder = ep_dir / "imagens"
    folder.mkdir(parents=True, exist_ok=True)
    provider = cfg.get_path("imagens.provedor", "placeholder")
    manifest = [{"arquivo": scene_name(s["id"]) + ".png", "plano": s["plano"], "seed": s["seed"],
                 "prompt": s["prompt_imagem"]} for s in board["cenas"]]
    (folder / "prompts.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    w, h = int(cfg.get_path("video.largura")), int(cfg.get_path("video.altura"))
    made, reused = 0, 0
    missing = []
    files = Manifest(folder)
    for sc in board["cenas"]:
        stem = scene_name(sc["id"])
        key = sha256_text(provider, sc["prompt_imagem"], str(sc["seed"]), f"{w}x{h}")
        found = _find(folder, stem, IMG_EXT)
        if found and files.reusable(stem, found, key):
            reused += 1
            continue
        if provider == "placeholder":
            _placeholder(folder / f"{stem}.png", w, h, f"Cena {sc['id']} - {sc['plano']}")
            files.record(stem, folder / f"{stem}.png", key, generated=True)
            made += 1
        elif provider == "a1111":
            _a1111(folder / f"{stem}.png", sc, cfg)
            files.record(stem, folder / f"{stem}.png", key, generated=True)
            made += 1
        else:  # externo
            missing.append(f"{stem}.png")
    if missing:
        raise StageResult("BLOCKED", f"provedor 'externo': gere as imagens a partir de imagens/prompts.json e salve "
                                     f"{len(missing)} arquivo(s) em {folder} (ex.: {missing[0]})")
    return {"provedor": provider, "geradas": made, "reaproveitadas": reused, "manifesto": str(folder / "prompts.json")}


def _placeholder(path: Path, w: int, h: int, label: str) -> None:
    try:
        from PIL import Image, ImageDraw
        img = Image.new("RGB", (w, h), (59, 47, 47))
        draw = ImageDraw.Draw(img)
        for y in range(h):  # degradê simples
            shade = int(40 + 60 * y / h)
            draw.line([(0, y), (w, y)], fill=(shade + 30, shade + 10, shade))
        draw.text((w // 3, h // 2), label, fill=(240, 220, 180))
        img.save(path)
    except ImportError:
        require_ffmpeg()
        run(["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi", "-i", f"color=c=0x3b2f2f:s={w}x{h}",
             "-frames:v", "1", str(path)])


def _a1111(path: Path, scene: dict, cfg) -> None:
    url = cfg.get_path("imagens.a1111_url", "http://127.0.0.1:7860").rstrip("/") + "/sdapi/v1/txt2img"
    body = {"prompt": scene["prompt_imagem"], "seed": scene["seed"], "steps": int(cfg.get_path("imagens.passos", 28)),
            "width": 1344, "height": 768,
            "negative_prompt": "texto, letras, marca d'água, deformado, sangue, violência gráfica, anacronismo"}
    req = urllib.request.Request(url, data=json.dumps(body).encode(), headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=600) as resp:
        data = json.loads(resp.read().decode())
    path.write_bytes(base64.b64decode(data["images"][0]))


# ------------------------------------------------------------------ narração
def spoken_for_tts(scene: dict, dictionary: dict) -> str:
    """Texto enviado à VOZ. A legenda continua usando scene['texto'].

    Prioridade: campo `pronuncia` da cena no storyboard.json; senão o dicionário [pronuncia] do TOML
    (palavra inteira, respeitando maiúsculas — nomes bíblicos são o caso comum).
    """
    if str(scene.get("pronuncia") or "").strip():
        return str(scene["pronuncia"]).strip()
    text = scene["texto"]
    if not dictionary:
        return text
    words = sorted(dictionary, key=len, reverse=True)
    pattern = rf"(?<!\w)({'|'.join(map(re.escape, words))})(?!\w)"
    return re.sub(pattern, lambda mt: str(dictionary[mt.group(1)]), text)


def make_narration(board: dict, ep_dir: Path, cfg) -> dict:
    folder = ep_dir / "audio"
    folder.mkdir(parents=True, exist_ok=True)
    provider = cfg.get_path("narracao.provedor", "silencio")
    wpm = float(cfg.get_path("video.palavras_por_minuto", 140))
    dictionary = cfg.get_path("pronuncia", {}) or {}
    made, reused, missing = 0, 0, []
    exe = {"piper": "piper", "edge": "edge-tts"}.get(provider)
    if exe and not shutil.which(exe):
        raise StageResult("BLOCKED", f"provedor '{provider}' escolhido mas o executável '{exe}' não está no PATH")
    if provider not in ("silencio", "piper", "edge", "externo"):
        raise StageResult("BLOCKED", f"provedor de narração desconhecido: '{provider}'")
    texts = {sc["id"]: spoken_for_tts(sc, dictionary) for sc in board["cenas"]}
    (folder / "textos.json").write_text(json.dumps(
        [{"arquivo": scene_name(s["id"]) + ".wav", "texto": texts[s["id"]]} for s in board["cenas"]],
        ensure_ascii=False, indent=2), encoding="utf-8")
    voice = {"piper": cfg.get_path("narracao.piper_modelo", ""),
             "edge": cfg.get_path("narracao.edge_voz", "pt-BR-AntonioNeural")}.get(provider, "")
    files = Manifest(folder)
    for sc in board["cenas"]:
        stem, text = scene_name(sc["id"]), texts[sc["id"]]
        key = sha256_text(provider, str(voice), text, str(wpm) if provider == "silencio" else "")
        found = _find(folder, stem, AUD_EXT)
        if found and files.reusable(stem, found, key):
            reused += 1
            continue
        target = folder / f"{stem}.{'mp3' if provider == 'edge' else 'wav'}"
        if provider == "silencio":
            require_ffmpeg()
            dur = max(1.0, len(text.split()) / wpm * 60)
            run(["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi", "-i", "anullsrc=r=44100:cl=mono",
                 "-t", f"{dur:.2f}", str(target)])
        elif provider == "piper":
            proc = subprocess.run(["piper", "--model", voice, "--output_file", str(target)],
                                  input=text, text=True, encoding="utf-8", capture_output=True)
            if proc.returncode != 0:
                target.unlink(missing_ok=True)
                raise RuntimeError(f"piper falhou: {proc.stderr[-300:]}")
        elif provider == "edge":
            try:
                run(["edge-tts", "--voice", str(voice), f"--text={text}", "--write-media", str(target)])
            except RuntimeError:
                target.unlink(missing_ok=True)  # não deixar áudio pela metade
                raise
        else:
            missing.append(f"{stem}.wav")
            continue
        files.record(stem, target, key, generated=True)
        made += 1
    if missing:
        raise StageResult("BLOCKED", f"provedor 'externo': grave/gere a narração a partir de audio/textos.json e salve "
                                     f"{len(missing)} arquivo(s) em {folder} (ex.: {missing[0]})")
    return {"provedor": provider, "geradas": made, "reaproveitadas": reused}


# ------------------------------------------------------------------ legendas
def _fmt_ts(sec: float) -> str:
    ms = int(round(sec * 1000))
    h, ms = divmod(ms, 3_600_000)
    m, ms = divmod(ms, 60_000)
    s, ms = divmod(ms, 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def build_srt(scenes_with_duration: list[tuple[str, float]], max_words: int = 12) -> str:
    """Legenda determinística: o tempo de cada bloco é proporcional às palavras dentro da cena."""
    out, idx, t = [], 1, 0.0
    for text, dur in scenes_with_duration:
        words = text.split()
        chunks = [words[i:i + max_words] for i in range(0, len(words), max_words)] or [[""]]
        total = sum(len(c) for c in chunks) or 1
        for chunk in chunks:
            seg = dur * len(chunk) / total
            out.append(f"{idx}\n{_fmt_ts(t)} --> {_fmt_ts(t + seg)}\n{' '.join(chunk)}\n")
            idx, t = idx + 1, t + seg
    return "\n".join(out)


# ------------------------------------------------------------------ render
def _motion_filter(motion: str, frames: int, w: int, h: int, fps: int) -> str:
    d = max(frames, 1)
    center = "x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)'"
    zooms = {
        "zoom_in": f"z='1+0.15*on/{d}':{center}",
        "zoom_in_slow": f"z='1+0.08*on/{d}':{center}",
        "zoom_out": f"z='1.15-0.15*on/{d}':{center}",
        "zoom_out_slow": f"z='1.08-0.08*on/{d}':{center}",
        "pan_right": f"z='1.12':x='(iw-iw/zoom)*on/{d}':y='ih/2-(ih/zoom/2)'",
        "tilt_up": f"z='1.12':x='iw/2-(iw/zoom/2)':y='(ih-ih/zoom)*(1-on/{d})'",
    }
    pre = f"scale={w * 2}:{h * 2}:force_original_aspect_ratio=increase,crop={w * 2}:{h * 2}"
    if motion == "dutch":
        pre += ",rotate=4*PI/180:fillcolor=black"
        z = f"z='1.18+0.04*on/{d}':{center}"
    else:
        z = zooms.get(motion, zooms["zoom_in_slow"])
    return f"{pre},zoompan={z}:d={d}:s={w}x{h}:fps={fps},format=yuv420p"


def render(board: dict, ep_dir: Path, cfg) -> dict:
    require_ffmpeg()
    w, h = int(cfg.get_path("video.largura")), int(cfg.get_path("video.altura"))
    fps, crf = int(cfg.get_path("video.fps", 25)), str(cfg.get_path("video.crf", 23))
    preset = cfg.get_path("video.preset", "veryfast")
    clips = ep_dir / "clipes"
    clips.mkdir(parents=True, exist_ok=True)
    durations: list[tuple[str, float]] = []
    for sc in board["cenas"]:
        stem = scene_name(sc["id"])
        img = _find(ep_dir / "imagens", stem, IMG_EXT)
        aud = _find(ep_dir / "audio", stem, AUD_EXT)
        if not img or not aud:
            raise StageResult("BLOCKED", f"faltando imagem ou áudio da {stem}")
        dur = probe_duration(aud)
        durations.append((sc["texto"], dur))
        out = clips / f"{stem}.mp4"
        motion = "dutch" if sc["plano"] == "dutch_angle" else sc["movimento"]
        key = sha256_text(sha256_file(img), sha256_file(aud), motion, f"{w}x{h}", str(fps), crf, str(preset))
        stamp = clips / f"{stem}.hash"
        if out.exists() and stamp.exists() and stamp.read_text() == key:
            continue  # clipe já renderizado com as mesmas entradas
        stamp.unlink(missing_ok=True)
        vf = _motion_filter(motion, math.ceil(dur * fps), w, h, fps)
        run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(img), "-i", str(aud),
             "-filter_complex", f"[0:v]{vf}[v]", "-map", "[v]", "-map", "1:a",
             "-c:v", "libx264", "-preset", preset, "-crf", crf, "-r", str(fps),
             "-c:a", "aac", "-b:a", "128k", "-ar", "44100", "-shortest", str(out)])
        stamp.write_text(key)
    concat_list = clips / "lista.txt"
    concat_list.write_text("".join(f"file '{scene_name(s['id'])}.mp4'\n" for s in board["cenas"]), encoding="utf-8")
    raw = ep_dir / "video_sem_legenda.mp4"
    run(["ffmpeg", "-y", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", str(concat_list),
         "-c", "copy", str(raw)])
    srt = ep_dir / "legendas.srt"
    srt.write_text(build_srt(durations), encoding="utf-8")
    final = ep_dir / "video.mp4"
    run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(raw), "-i", str(srt), "-map", "0", "-map", "1",
         "-c", "copy", "-c:s", "mov_text", "-metadata:s:s:0", "language=por", str(final)])
    thumb = make_thumbnail(board, ep_dir)
    total = sum(d for _, d in durations)
    return {"video": str(final), "legendas": str(srt), "thumbnail": thumb, "duracao_s": round(total, 2),
            "cenas": len(durations), "preset": preset, "crf": crf}


def make_thumbnail(board: dict, ep_dir: Path) -> str | None:
    """Imagem forte + 2–3 palavras grandes. Prefere uma cena de ângulo baixo ou close-up."""
    pick = next((s for s in board["cenas"] if s["plano"] in ("low_angle", "close_up")), board["cenas"][0])
    img_path = _find(ep_dir / "imagens", scene_name(pick["id"]), IMG_EXT)
    target = ep_dir / "thumbnail.png"
    try:
        from PIL import Image, ImageDraw, ImageFont
    except ImportError:
        if img_path:
            shutil.copy(img_path, target)
        return str(target) if img_path else None
    img = Image.open(img_path).convert("RGB")
    img = img.resize((1280, int(1280 * img.height / img.width))).crop((0, 0, 1280, 720))
    draw = ImageDraw.Draw(img)
    text = str(board.get("texto_thumbnail") or "").upper()
    font = None
    for candidate in ("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", "C:/Windows/Fonts/arialbd.ttf",
                      "/System/Library/Fonts/Supplemental/Arial Bold.ttf"):
        if Path(candidate).exists():
            font = ImageFont.truetype(candidate, 120)
            break
    if font is None:
        try:
            font = ImageFont.load_default(size=120)
        except TypeError:
            font = ImageFont.load_default()
    draw.text((60, 520), text, font=font, fill=(255, 215, 0), stroke_width=6, stroke_fill=(0, 0, 0))
    img.save(target)
    return str(target)
