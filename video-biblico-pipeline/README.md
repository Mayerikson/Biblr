# Video Bíblico Pipeline

**Da pauta ao vídeo educativo pronto, com IA fazendo o trabalho pesado e uma pessoa revisando o que importa.**

Pipeline local-first que transforma título + tema + referências bíblicas em vídeo longo de narrativa (imagem + narração):
roteiro validado → storyboard com enquadramentos cinematográficos → **aprovação humana** → imagens → narração →
render com movimento de câmera, legendas e thumbnail → publicação privada/agendada no YouTube.

> Novo por aqui (pessoa ou IA)? Comece por **[HANDOFF.md](HANDOFF.md)**.

## Por que existe
Canais "dark" 100% automáticos rendem centavos por mil views e estão na mira da política de conteúdo inautêntico do
YouTube. Este projeto aposta no oposto: conteúdo educativo, fiel ao texto, com direção visual e revisão humana —
e usa o canal como topo de funil para produtos de maior valor (ver [docs/STRATEGY.md](docs/STRATEGY.md)).

## Princípios
- **Determinístico primeiro:** validação, regras de enquadramento, legendas e estado em Python; LLM só redige.
- **Gate humano obrigatório**, selado por hash do conteúdo aprovado.
- **DRY_RUN por padrão**; publicação real só com `--live` e sempre privada/agendada.
- **Model-portable:** Ollama, LM Studio, Groq, OpenRouter, Gemini — troca no TOML.
- **Bounded efficiency:** orçamento por execução, cache, idempotência, no máximo 2 tentativas.
- **Explicável e observável:** run_id, eventos JSONL, `run_summary.json`, `*.explain.json`.

## Requisitos
Python ≥ 3.11 e ffmpeg no PATH. Opcionais: `pip install -r requirements-optional.txt` (Pillow e YouTube API).

## Começo rápido
```bash
python scripts/vbp.py doctor
python scripts/vbp.py demo                       # ponta a ponta sem internet; vídeo em workspace-demo/
python scripts/vbp.py init                       # cria config/pipeline.toml e .env
python scripts/vbp.py import-pauta data/pauta.example.csv
python scripts/vbp.py run -e EP001               # para no gate humano
python scripts/vbp.py approve EP001 --por "Seu Nome"
python scripts/vbp.py run -e EP001               # mídia + render + publish_plan (DRY_RUN)
python scripts/vbp.py explain EP001 --timeline
python scripts/vbp.py report
```

## Testes
```bash
pip install -r requirements-dev.txt
python -m pytest -q        # 50 testes offline (LLM fake, ffmpeg real)
```

## Documentação
| Arquivo | Conteúdo |
|---|---|
| [HANDOFF.md](HANDOFF.md) | contexto da conversa, estado real, próximos passos, prompt de continuidade |
| [AGENTS.md](AGENTS.md) | regras para qualquer IA que trabalhar no repositório |
| [docs/DECISIONS.md](docs/DECISIONS.md) | ADRs: decisões, alternativas, justificativas, riscos |
| [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) | componentes, fluxo, extensões |
| [docs/OBSERVABILITY.md](docs/OBSERVABILITY.md) | logs, métricas, explicações, health check |
| [docs/EFFICIENCY.md](docs/EFFICIENCY.md) | orçamento, medido × estimado |
| [docs/RESEARCH.md](docs/RESEARCH.md) | política do YouTube, mercado, fontes |
| [docs/STRATEGY.md](docs/STRATEGY.md) | modelo de negócio e validação |
| [docs/REUSE.md](docs/REUSE.md) | o que veio do Fitness-Manager, jobs-engine e Spec |
| [docs/RUNBOOK.md](docs/RUNBOOK.md) | rotina semanal e solução de problemas |
| [tasks/prd-pipeline-video-v1/](tasks/prd-pipeline-video-v1/) | PRD, TechSpec e tarefas (SDD) |

## Licença
Ainda não definida pelo owner.
