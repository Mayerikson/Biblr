# Explainability & Observability

Proporcional ao risco (MYK): projeto local, um operador, sem dados pessoais de terceiros. Por isso: logs estruturados,
correlation ID, métricas por execução, explicação por artefato e health check. Sem stack de APM, alertas ou SLO — ainda.

## 1. Correlação
Toda execução recebe `run_id` (`AAAAMMDD-HHMMSS-xxxxxx`). Ele aparece em cada evento, no SQLite, no `run_summary.json`,
nos `*.explain.json` e nos diagnósticos. Para rastrear um problema: `vbp explain EP001 --timeline`.

## 2. Eventos (logs estruturados)
- Arquivo: `workspace/runs/<run_id>/events.jsonl` (uma linha JSON por evento) + espelho na tabela `events` (append-only).
- Esquema:

| Campo | Exemplo | Observação |
|---|---|---|
| `ts` | `2026-11-26T09:08:50-03:00` | fuso America/Sao_Paulo |
| `run_id` | `20261126-090850-bf7606` | correlation ID |
| `mode` | `DRY_RUN` / `LIVE` | ambiente lógico |
| `episode`, `stage` | `EP001`, `ROTEIRO` | opcionais |
| `event` | `stage_start`, `stage_end`, `llm_call`, `llm_cache_hit`, `llm_failure`, `script_retry`, `images_done`… | |
| `status` | `PASS`/`FAIL`/`BLOCKED`/`SKIPPED` | em `stage_end` e falhas |
| `data` | `{"provider": "local", "tokens_est": 3100}` | **redigido**: chaves com key/token/secret/senha viram `***`; padrões de chave (AIza…, sk-…, gsk_…, token Telegram) são mascarados |

## 3. Métricas por execução (`run_summary.json`)
`llm_calls`, `llm_cache_hits`, `llm_failures`, `fallbacks`, `retries`, `tokens_est` (**estimado**), `cost_brl_est` (**estimado**),
duração de cada etapa (**medida**), contagem por status e uso do orçamento (limites × usado).
Consulta: `vbp report --ultimos 10`.

## 4. Explicabilidade (por que o sistema decidiu assim)
Cada artefato importante tem um irmão `.explain.json`:

| Arquivo | Explica |
|---|---|
| `roteiro.json.explain.json` | provedor/modelo usado, se veio do cache, cada tentativa com todos os checks PASS/FAIL, feedback humano aplicado |
| `storyboard.json.explain.json` | por cena: plano escolhido, **regra** e **palavra-gatilho**, personagens detectados; distribuição de planos; resultado do LLM de descrição |
| `video.mp4.explain.json` | duração, cenas, preset/CRF, movimentos por plano |
| `diagnostico_<etapa>.json` | motivo do bloqueio/falha, orçamento usado, métricas, próximo passo |
| `roteiro.rejeitado.json` | versões reprovadas e os checks que falharam |
| `REVISAO.txt` | resumo para o revisor humano |

`vbp explain EP001` mostra tudo isso no terminal.

## 5. Health check
`vbp doctor` → PASS/FAIL/NOT_RUN para Python, ffmpeg/ffprobe, Pillow, config, chaves de provedores (só presença, nunca o valor)
e workspace gravável. Não chama APIs pagas (custo).

## 6. Status padronizados
`PASS` concluiu · `FAIL` erro inesperado (gera diagnóstico) · `BLOCKED` parada esperada que precisa de ação
(gate humano, orçamento, arquivo externo faltando) · `SKIPPED` nada mudou desde a última execução · `NOT_RUN` não verificado.

## 7. Lacunas conhecidas (evoluir quando houver necessidade)
- Sem alertas automáticos (sugestão: mensagem no Telegram quando uma execução terminar em FAIL/BLOCKED).
- Sem métricas pós-publicação (YouTube Analytics: retenção média, CTR, inscritos por vídeo) — essenciais no mês 3.
- Custos são estimativas por caracteres; medir com o `usage` retornado pelas APIs quando usar provedores pagos.
