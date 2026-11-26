"""Respostas determinísticas para `vbp demo` e para os testes (sem internet, sem custo).

O texto é um ESQUELETO DE DEMONSTRAÇÃO para exercitar o pipeline — não é conteúdo para publicar.
"""
from __future__ import annotations

import json
import re

FRASES = [
    "No vale de Elá, dois exércitos se encaram em silêncio ({ref}).",
    "O gigante desafia Israel todos os dias, e ninguém responde ({ref}).",
    "Um menino pastor chega com pão para os irmãos e ouve o desafio ({ref}).",
    "Ele viu o que os soldados não queriam ver: a afronta ao nome de Deus ({ref}).",
    "Com a mão firme, escolheu cinco pedras lisas no riacho ({ref}).",
    "O rei ofereceu sua armadura, mas o menino preferiu o que conhecia ({ref}).",
    "A multidão no acampamento prendeu a respiração ({ref}).",
    "A história ensina que a coragem nasce da confiança, não do tamanho ({ref}).",
]


def _dados(prompt: str) -> dict:
    m = re.search(r"=== DADOS DO EPISÓDIO ===\s*(\{.*?\})\s*===", prompt, re.S)
    return json.loads(m.group(1)) if m else {"titulo": "Episódio demo", "referencias": "1 Samuel 17"}


def _alvo(prompt: str) -> int:
    m = re.search(r"aprox\. (\d+) palavras", prompt)
    return int(m.group(1)) if m else 300


def _secoes(prompt: str) -> int:
    m = re.search(r"Use entre (\d+) e (\d+) seções", prompt)
    return int(m.group(1)) if m else 6


def responder(prompt: str) -> str:
    if prompt.startswith("ETAPA: storyboard"):
        ids = re.findall(r"^(\d+) \| ", prompt, re.M)
        return json.dumps({"cenas": [{"id": int(i), "descricao": f"Composição da cena {i}, fiel ao texto e à época"}
                                     for i in ids]}, ensure_ascii=False)
    dados = _dados(prompt)
    refs = [r.strip() for r in str(dados.get("referencias", "1 Samuel 17")).split(";") if r.strip()] or ["1 Samuel 17"]
    n_sec, alvo = _secoes(prompt), _alvo(prompt)
    por_secao = max(10, (alvo - 40) // n_sec)
    secoes = []
    k = 0
    for i in range(n_sec):
        frases: list[str] = []
        while len(" ".join(frases).split()) < por_secao:
            frases.append(FRASES[k % len(FRASES)].format(ref=refs[k % len(refs)]))
            k += 1
        secoes.append({"titulo": f"Parte {i + 1}", "texto": " ".join(frases)})
    data = {
        "titulo": str(dados.get("titulo", "Episódio demo"))[:70],
        "texto_thumbnail": "CORAGEM REAL",
        "gancho": "Por que um exército inteiro tremeu diante de um homem só? A resposta está no texto.",
        "secoes": secoes,
        "conclusao": "Coragem, na Bíblia, é confiar em Deus diante do impossível. Pense nisso esta semana.",
        "descricao_youtube": "Episódio de demonstração. Referências: " + "; ".join(refs),
    }
    return json.dumps(data, ensure_ascii=False)
