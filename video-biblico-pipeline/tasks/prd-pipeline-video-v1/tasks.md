# Resumo das tarefas de implementação — Pipeline de Vídeo Bíblico v1

> **Status do plano:** `DRAFT`. Tarefas 1–8 entregues como protótipo 0.1.0 (spike, antes da aprovação formal — desvio declarado no HANDOFF).

## Tarefas

- [x] 1.0 Núcleo: config, estado SQLite, observabilidade, orçamento — CA-11, CA-12, CA-13 — TU-04, TU-05
- [x] 2.0 Camada de LLM portátil (fallback, circuit breaker, cache) — CA-11, CA-12 — TU-04
- [x] 3.0 Roteiro: prompt editorial, validação, regeneração limitada — CA-01, CA-02, CA-03 — TU-01, TU-02, TI-03
- [x] 4.0 Storyboard por regras + ficha de personagens — CA-04, CA-05 — TU-03
- [x] 5.0 Gate humano selado por hash (CLI + Telegram) — CA-06, CA-07, CA-08 — TI-01, TI-02
- [x] 6.0 Mídia: imagens/narração plugáveis, render ffmpeg, SRT, thumbnail — CA-09 — E2E-01, TI-05
- [x] 7.0 Publicação DRY_RUN/LIVE privada — CA-10 — SEC-01
- [x] 8.0 CLI, demo, CI, documentação e handoff — todos
- [ ] 9.0 Validar com LLM local real (Ollama) e ajustar prompts até ≥ 80% dos roteiros passarem na 1ª tentativa — CA-03
- [ ] 10.0 Provedor de imagens real (ComfyUI ou A1111) + consistência de personagem (LoRA/referência) — CA-05
- [ ] 11.0 Escolher e integrar TTS (qualidade + licença comercial) ou fluxo de gravação da voz do owner — RF11
- [ ] 12.0 OAuth do YouTube e primeiro upload privado real (QA manual) — CA-10
- [ ] 13.0 Alertas no Telegram para FAIL/BLOCKED e coleta de métricas do YouTube Analytics — OBJ-5
- [ ] 14.0 Review independente (outra pessoa/IA em sessão separada) — gate de release
