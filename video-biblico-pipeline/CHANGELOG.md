# Changelog

## 0.1.0 — 2026-11-26 (protótipo)
- Pipeline completo pauta → roteiro → storyboard → gate humano → imagens → narração → render → publicação (DRY_RUN).
- Camada de LLM portátil com fallback, circuit breaker, cache e orçamento.
- Validação determinística de roteiro e de referências bíblicas (66 livros).
- Storyboard por regras de enquadramento com explicação por cena e ficha de personagens.
- Aprovação selada por SHA-256; ajuste humano vira feedback; Telegram opcional.
- Render ffmpeg com movimento por plano, legenda embutida e thumbnail.
- Observabilidade (run_id, eventos JSONL/SQLite, run_summary, explain, doctor) e documentação SDD/handoff.
- 34 testes offline + CI no GitHub Actions.
