# HANDOFF — Video Bíblico Pipeline

> Documento de continuidade para qualquer pessoa ou IA (Claude, ChatGPT, Gemini, Codex, Cursor…) que assumir o projeto.
> **Leia este arquivo inteiro antes de propor qualquer mudança.** Depois leia `AGENTS.md` e `docs/DECISIONS.md`.

**Versão:** `0.1.0` (protótipo funcional) · **Data do handoff:** 2026-11-26 · **Idioma:** português do Brasil
**Estado SDD:** PRD, TechSpec e plano em **rascunho — pendentes de aprovação do owner** (ver seção 9).

---

## 1. Resumo em 30 segundos

O owner (programador, faz automação com Python/APIs/GitHub Actions) quer gerar renda com conteúdo automatizado por IA.
Depois de analisar o mercado de "canais dark", a decisão foi **não** fazer uma fábrica de vídeos genéricos, e sim:

1. Um **canal educativo de narrativas bíblicas** (vídeos longos, imagem + narração, storyboard cinematográfico),
   produzido por este pipeline com **revisão teológica humana obrigatória**;
2. Usar o canal como **topo de funil** para um produto de **ticket alto em coprodução** (formação para pastores/líderes),
   onde um especialista entra com autoridade e o owner entra com conteúdo, funil e automação.

Este repositório é a **máquina de produção** (item 1). O item 2 ainda está em fase de validação (entrevistas).

## 2. Como a decisão foi tomada (contexto da conversa)

| Etapa | O que o owner trouxe | Conclusão |
|---|---|---|
| 1 | Post do LinkedIn: canal dark 100% IA com 30M de views no 1º mês | Nos comentários, o autor revelou **R$885** de receita no mês → ~R$0,03 por mil views (Shorts). Viralizar não paga sozinho; há viés de sobrevivência. |
| 2 | Comentários: canais banidos, canais que "morreram do nada" após R$40k | Audiência alugada do algoritmo some quando ele muda. Política do YouTube endureceu em 2026 (ver `docs/RESEARCH.md`). |
| 3 | Comentário de Rafael Targino: só 2 jeitos de monetizar conteúdo bom | (a) conexão + entretenimento com valor; (b) nicho de ticket alto com proposta de valor forte. Caminho (b) escolhido como principal. |
| 4 | Perfil do owner (perguntas objetivas) | Objetivo: **testar e aprender**. Tempo: **5–15 h/semana**. Orçamento: **R$100–500/mês**. Habilidade: **programação/automação**. |
| 5 | "Canal evangélico é o maior nicho" | Público enorme (Censo 2022: 26,9%), mas saturado de fábricas de isca emocional. Ângulo escolhido: **educativo** (contexto histórico, personagens, geografia), não devocional genérico. |
| 6 | Owner é do público-alvo (evangélico) | Vantagem: valida teologia, fala a língua, tem rede (igreja). Vira o **controle de qualidade teológico** do pipeline. |
| 7 | Aula "Tríade A.E.I." (Autoridade, Entretenimento, Informação) | IA automatiza bem o **I**, parcialmente o **E**, quase nada do **A**. Canal dark puro = só I → morre. Modelo híbrido: máquina faz o I; camada humana leve faz A e E (voz, nome, testemunhos, bastidores). |
| 8 | PDF "Estudo de caso do 0 aos 5 dígitos" (canal de filosofia, imagem + narração, 30 min/dia) | **Copiar:** formato longo, thumbnail imagem + 2–3 palavras, estrutura de roteiro com ganchos/transições, padrões de título. **Não copiar:** atribuições inventadas a autoridades, prompt de fofoca ("rumores/controvérsias"), "censura" para driblar diretrizes. Ver ADR-011. |
| 9 | Slide "Religião em coprodução" (formação para pastores circulada) | Ideia mais forte do conjunto: ticket alto + autoridade de terceiro + habilidades do owner. Cuidados: credibilidade do coprodutor, diferenças doutrinárias, não competir com seminários (focar no prático). |
| 10 | Material de storyboard (12 tipos de enquadramento) | Vira o "diretor automático": regras palavra-gatilho → plano (ângulo baixo = poder, alto = vulnerabilidade, close = detalhe…). Diferencia das fábricas de slideshow. |
| 11 | Repositórios do owner (Fitness-Manager, digisystem-jobs-engine, Spec) | Padrões reaproveitados: pipeline coletar→planejar→redigir→validar→publicar, DRY_RUN padrão, fallback com circuit breaker, Telegram com allowlist e confirmação, LLM local, SQLite append-only, método SDD. Ver `docs/REUSE.md`. |

## 3. O que o produto é (e não é)

**É:** pipeline local-first que transforma uma pauta (título, tema, referências bíblicas) em vídeo pronto:
roteiro validado → storyboard com enquadramentos → **aprovação humana** → imagens → narração → render com
movimento de câmera, legendas e thumbnail → publicação no YouTube (privado/agendado).

**Não é:** gerador de "slop", bot de isca emocional, nem sistema que publica sem uma pessoa revisar.

## 4. Estado do desenvolvimento (honesto)

### Implementado e testado (PASS — evidência: `python -m pytest` = 34 testes; `python scripts/vbp.py demo`)
- Estado em SQLite: episódios, eventos **append-only** (triggers impedem UPDATE/DELETE), artefatos com hash de entrada, aprovações, cache de LLM.
- Camada de LLM portátil: `openai_compat` (Ollama/LM Studio/Groq/OpenRouter), `gemini`, `fake`; fallback com circuit breaker; cache por hash; extração robusta de JSON.
- Roteiro: prompt com guia editorial, validação determinística (campos, 6–8 seções, referência por seção, livro/capítulo válidos, frases de isca proibidas, duração estimada), regeneração com feedback limitada a 2 tentativas, diagnóstico ao bloquear.
- Storyboard: divisão em cenas, regras de enquadramento com explicação (regra + palavra-gatilho), restrição de variedade, ficha de personagens com seed fixa, LLM só descreve composição (não pode trocar plano), degradação graciosa se o LLM falhar.
- Gate humano: aprovação selada por SHA-256 de roteiro+storyboard; mudou o conteúdo → aprovação perde validade; pedido de ajuste volta como feedback para o LLM.
- Mídia: imagens placeholder/externo, narração silêncio/externo, render ffmpeg por cena com Ken Burns por plano (H.264 veryfast), concat, legenda SRT embutida, thumbnail com texto.
- Publicação em **DRY_RUN** (gera `publish_plan.json`); envio sempre `private` + `containsSyntheticMedia`.
- Observabilidade: run_id, eventos JSONL + SQLite, `run_summary.json`, `*.explain.json`, `vbp report`, `vbp explain --timeline`, `vbp doctor`, redação de segredos.
- Orçamento por execução (chamadas, tokens estimados, custo, tentativas, cenas, tempo) → BLOCKED com diagnóstico.
- CI no GitHub Actions (testes + demo).

### Implementado, mas NOT_RUN (sem ambiente para testar aqui)
- Chamada real a Ollama/LM Studio/Groq/Gemini (código pronto; testado só com provedor fake).
- Provedor de imagens `a1111` (API Automatic1111/Forge) — confirmar payload com a sua versão.
- Narração `piper` (TTS local).
- Upload real no YouTube (`--live`), thumbnail e legenda via API — exige OAuth do Google. Confirmar que o campo `status.containsSyntheticMedia` é aceito pela versão atual da API.
- Telegram (`telegram-review` / `telegram-poll`).

### Não implementado (próximos passos sugeridos)
- Provedor de imagem ComfyUI e LoRA de personagem para consistência forte.
- TTS de melhor qualidade (avaliar opções locais/pagas e licença comercial da voz).
- Bot de devocional diário (WhatsApp/Telegram) — esqueleto existe no Fitness-Manager.
- Métricas pós-publicação (YouTube Analytics: retenção, CTR) para fechar o ciclo de aprendizado.
- Página de captura / lista própria (audiência que não depende do algoritmo).

## 5. Estrutura do repositório

```
vbp/            código (config, obs, budget, state, llm, bible_refs, script, storyboard, media, approval, publish, pipeline, cli, demo)
prompts/        editorial.md (regras do canal), roteiro.md, storyboard.md, revisao.md (checklist humano)
config/         pipeline.example.toml (copie para pipeline.toml)
data/           pauta.example.csv (5 episódios de exemplo)
tests/          34 testes offline (unidade, integração, E2E com ffmpeg real)
docs/           DECISIONS (ADRs), ARCHITECTURE, OBSERVABILITY, EFFICIENCY, RESEARCH, STRATEGY, REUSE, RUNBOOK
tasks/prd-pipeline-video-v1/   prd.md, techspec.md, tasks.md (padrão SDD do owner)
```

## 6. Como rodar

```bash
python scripts/vbp.py doctor          # health check
python scripts/vbp.py demo            # ponta a ponta, sem internet, sem custo (vídeo em workspace-demo/)
python scripts/vbp.py init            # cria config/pipeline.toml e .env
python scripts/vbp.py import-pauta data/pauta.example.csv
python scripts/vbp.py run -e EP001    # para no gate humano
# leia workspace/episodios/EP001/roteiro.md com prompts/revisao.md
python scripts/vbp.py approve EP001 --por "Seu Nome"     # ou: reject EP001 --motivo "..."
python scripts/vbp.py run -e EP001    # imagens → narração → render → publish_plan (DRY_RUN)
python scripts/vbp.py explain EP001 --timeline
python scripts/vbp.py report
```

## 7. Plano de 90 dias (acordado na conversa)

- **Mês 1:** pipeline mínimo rodando com LLM local + imagens reais; protótipo do bot devocional testado com 10–20 pessoas da igreja.
- **Mês 2:** 3–4 vídeos/semana; making-of semanal no LinkedIn; GitHub como vitrine.
- **Mês 3:** decidir com dados (retenção, não views): canal (vídeo longo, talvez versão em inglês), bot (audiência própria) ou serviço/coprodução.
- **Em paralelo (validação do negócio):** conversar com 5–10 pastores ("qual a maior dificuldade do ministério que ninguém te ensinou?"); mapear 1–2 possíveis coprodutores; aula ao vivo gratuita como teste.

## 8. Perguntas em aberto (decisões do owner)

1. Qual tradução bíblica usar e qual licença permite uso em vídeo? (Hoje: parafrasear + citar referência; citação ≤ 25 palavras.)
2. Voz: TTS (qual, licença comercial?) ou a voz do próprio owner (mais autoridade — tríade A.E.I.)?
3. Nome, identidade visual e estilo de imagem do canal.
4. Começar só em português (revisão teológica mais segura) e avaliar inglês depois? (Recomendação: sim.)
5. Quanto de "camada humana" (voz, nome, bastidores) o owner topa expor?
6. Coprodução: quem é o especialista? Qual o recorte (pregação, liderança, aconselhamento, gestão, comunicação/mídia para igrejas)?

> Privacidade: este handoff menciona contexto pessoal do owner (fé, orçamento). Se o repositório for público, avalie deixar este arquivo genérico ou o repositório privado.

## 9. Gates SDD (padrão MYK do owner)

| Gate | Status | Observação |
|---|---|---|
| PRD | `DRAFT` | `tasks/prd-pipeline-video-v1/prd.md` — aguardando aprovação do owner |
| TechSpec | `DRAFT` | reflete o protótipo 0.1.0 |
| Plano de tarefas | `DRAFT` | tasks 1–8 implementadas como protótipo; 9+ pendentes |
| QA | `PARTIAL` | testes automatizados PASS; itens NOT_RUN listados na seção 4 |
| Review independente | `NOT_RUN` | `independent: false` — mesmo agente implementou e revisou |
| Release/produção | `BLOCKED` | exige aprovação do owner, OAuth do YouTube e QA dos itens NOT_RUN |

**Desvio de processo declarado:** o código 0.1.0 foi escrito antes da aprovação formal do PRD, como **spike/protótipo**
para validar a viabilidade técnica. Nenhuma aprovação retroativa foi inventada.

## 10. Prompt de continuidade (cole em qualquer IA)

```
Você vai continuar o projeto "Video Bíblico Pipeline". Antes de qualquer coisa, leia nesta ordem:
HANDOFF.md, AGENTS.md, docs/DECISIONS.md, tasks/prd-pipeline-video-v1/prd.md e techspec.md.
Regras: siga as ADRs aprovadas; não remova o gate humano nem o DRY_RUN padrão; não exponha segredos;
toda mudança de comportamento precisa de teste (python -m pytest) e de atualização do HANDOFF (seção 4) e do CHANGELOG.
Relate resultados como PASS/FAIL/BLOCKED/NOT_RUN, separando o que foi medido do que foi estimado.
Minha tarefa agora é: <descreva aqui>
```
