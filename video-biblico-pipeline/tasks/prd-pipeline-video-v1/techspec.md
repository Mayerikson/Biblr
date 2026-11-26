# Especificação técnica — Pipeline de Vídeo Bíblico v1

> **Status:** `DRAFT` — reflete o protótipo 0.1.0; aguarda aprovação do owner. Requisitos em `prd.md`.

## Resumo

Aplicação Python CLI local-first, sem dependências obrigatórias além de ffmpeg. Um orquestrador executa etapas
idempotentes sobre um estado SQLite; LLMs são acessados por uma camada portátil com fallback, cache e orçamento;
decisões de enquadramento e validações são determinísticas; um gate humano selado por hash separa geração de
conteúdo e produção de mídia. Detalhes de arquitetura em `docs/ARCHITECTURE.md`; decisões em `docs/DECISIONS.md`.

## Arquitetura do sistema

### Visão dos componentes
- `Pipeline` (orquestrador) → `script`, `storyboard`, `approval`, `media`, `publish`.
- `LLMClient` (fallback/cache/orçamento) → provedores `OpenAICompat`, `Gemini`, `FakeProvider`.
- `State` (SQLite), `Observer` (eventos/métricas/explicações), `Budget` (limites), `Config` (TOML + env).

## Design de implementação

### Principais interfaces
```
Pipeline.run(ep_id, until=None, publish_at=None) -> run_summary: dict
LLMClient.json(prompt, temperature, stage, episode) -> (data, provenance)
validate_script(script, cfg) -> list[{check, status, detail}]
build_storyboard(script, cfg) -> (board, explain)
approval.approve(state, ep_id, ep_dir, approver) -> content_hash
media.render(board, ep_dir, cfg) -> {video, legendas, thumbnail, duracao_s}
```

### Modelos de dados

#### `Roteiro` — saída do LLM validada
| Campo | Tipo | Obrigatório | Descrição |
|---|---|---|---|
| `titulo` | string ≤ 70 | sim | título do vídeo |
| `texto_thumbnail` | string (1–3 palavras) | sim | texto da thumbnail |
| `gancho` | string | sim | abertura |
| `secoes` | lista[{titulo, texto}] (6–8) | sim | cada texto com ≥ 1 "(Livro cap:vers)" |
| `conclusao` | string | sim | aplicação/reflexão |
| `descricao_youtube` | string | sim | resumo + referências |

#### `Cena` — item de `storyboard.json`
| Campo | Tipo | Descrição |
|---|---|---|
| `id` | int | 1..N |
| `origem` | string | gancho / secao_N / conclusao |
| `texto` | string | narração (sem referências entre parênteses) |
| `referencias` | lista[string] | referências removidas da fala |
| `plano` | enum | wide, medium, close_up, low_angle, high_angle, birds_eye, dutch_angle, pov |
| `movimento` | enum | zoom_in, zoom_in_slow, zoom_out, zoom_out_slow, pan_right, tilt_up |
| `personagens` | lista[{id, descricao, seed}] | da ficha |
| `seed` | int | seed do personagem principal ou 1000+id |
| `prompt_imagem` | string | plano + descrição + personagens + estilo |

#### Tabelas SQLite
`episodes`, `events` (append-only por trigger), `artifacts` (episode_id, stage, path, input_hash),
`approvals` (decision, approver, content_hash, note), `llm_cache` (key=sha256(provedor, modelo, temperatura, prompt)), `kv`.

### Estados do episódio
`PAUTA → ROTEIRO → STORYBOARD → AGUARDANDO_APROVACAO → APROVADO → IMAGENS → NARRACAO → PRONTO → PUBLICADO`
(+ `AJUSTE_SOLICITADO`).

## Segurança
Segredos via env; redação de logs; allowlist no Telegram; publicação com dupla verificação de aprovação; respostas de
LLM tratadas como dados não confiáveis (validação antes de persistir); upload privado + mídia sintética declarada.

## Observabilidade e eficiência
Ver `docs/OBSERVABILITY.md` e `docs/EFFICIENCY.md`.

## Testes

| ID | Caso | Arquivo |
|---|---|---|
| TU-01 | referências válidas/inválidas, Jó×Jo, extração entre parênteses | `tests/test_units.py` |
| TU-02 | validação do roteiro (isca, seção sem ref, ref inválida, nº de seções), fala sem referências | `tests/test_units.py` |
| TU-03 | regra de plano + explicação, variedade, personagem/seed, LLM não troca plano | `tests/test_units.py` |
| TU-04 | extração de JSON, fallback + circuit breaker + cache, orçamento antes da chamada | `tests/test_units.py` |
| TU-05 | append-only, idempotência de episódio, redação, span/resumo, SRT | `tests/test_units.py` |
| E2E-01 | gate → aprovação → render (3 faixas) → publish DRY_RUN; 2ª execução sem LLM | `tests/test_pipeline.py` |
| TI-01 | alteração pós-aprovação invalida | `tests/test_pipeline.py` |
| TI-02 | ajuste humano vira feedback | `tests/test_pipeline.py` |
| TI-03 | validação falha 2× → BLOCKED + diagnóstico | `tests/test_pipeline.py` |
| TI-04 | orçamento zero → BLOCKED | `tests/test_pipeline.py` |
| TI-05 | provedor externo → BLOCKED com instrução | `tests/test_pipeline.py` |
| SEC-01 | `--live` sem aprovação nunca publica | `tests/test_pipeline.py` |
