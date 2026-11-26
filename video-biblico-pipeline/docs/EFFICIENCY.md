# Bounded Efficiency

Princípio (MYK): considerar tokens, tempo, custo, latência, memória, manutenção e complexidade; limitar tentativas;
após repetição, diagnosticar; **eficiência nunca remove controles críticos** (o gate humano não é "otimizado").

## 1. Limites por execução (`[orcamento]` no TOML)

| Limite | Padrão | Ao estourar |
|---|---|---|
| `max_chamadas_llm` | 30 | etapa `BLOCKED` + diagnóstico |
| `max_tokens_estimados` | 200.000 | verificado **antes** da chamada |
| `max_custo_brl` | R$ 5,00 | verificado após cada chamada |
| `max_tentativas_por_etapa` | 2 | 2ª tentativa recebe o feedback da 1ª; depois, diagnóstico |
| `max_cenas` | 120 | protege render e geração de imagens |
| `max_segundos_execucao` | 3600 | protege contra travamentos |

## 2. Mecanismos que evitam desperdício
- **Idempotência por hash de entrada:** etapa sem mudança = `SKIPPED` (0 custo).
- **Cache de LLM por hash do prompt:** a mesma pergunta nunca é paga duas vezes.
- **Circuit breaker:** provedor que falhou sai da cadeia pelo resto da execução (sem retentar o que está fora do ar).
- **Regras antes de LLM** no storyboard (ADR-004).
- **Render incremental:** clipe de cena só é refeito se a imagem ou o áudio forem mais novos.
- **H.264 `veryfast`:** presets mais lentos custam 2–3× o tempo para ganho pequeno neste formato.

## 3. Medido × estimado × não medido

| Item | Valor | Tipo |
|---|---|---|
| Suíte de testes (34 testes, ffmpeg real) | ~5 s | **medido** (ambiente de desenvolvimento) |
| Demo: vídeo de 60 s, 640×360, 15 fps, 8 cenas | ~4 s ponta a ponta | **medido** |
| 2ª execução após aprovação | 0 chamadas de LLM | **medido** (teste E2E) |
| Tokens por roteiro | ~3.000 de entrada + margem de 2.000 | **estimado** (caracteres ÷ 3) |
| Custo com LLM local | R$ 0 de API (custo é energia/hardware) | **estimado** |
| Render de 20 min em 1080p | não medido; tende a crescer com resolução × duração | **não medido** |
| Geração de imagens locais (~60–80 cenas/vídeo) | depende da GPU | **não medido** |

## 4. Orçamento mensal sugerido (dentro de R$100–500)
LLM local (R$0) com fallback barato; imagens locais na GPU própria ou serviço pago só se necessário; TTS é o item mais
caro a decidir (ver HANDOFF, perguntas em aberto). Registre o custo real medido em `run_summary.json` antes de escalar.

## 5. Complexidade evitada de propósito
Sem Airflow, Kafka, filas, containers obrigatórios ou runtime de agentes. Um processo, um SQLite, um CLI (ADR-013).
