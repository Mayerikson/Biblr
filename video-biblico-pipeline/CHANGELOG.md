# Changelog

## 0.2.0 — 2026-11-27
Correções:
- Áudio e imagem antigos eram reaproveitados depois de o roteiro mudar; agora o cache é por conteúdo (o velho vai para `_antigos/`).
- Clipes eram reaproveitados mesmo mudando resolução ou movimento.
- Rodar `--live` de novo podia reenviar o mesmo vídeo.
- Resposta de LLM reprovada ficava no cache e travava as execuções seguintes.
- `demo` falhava na segunda execução; `init` quebrava sem `.env.example`.
- JSON do LLM em formato inesperado derrubava a etapa; Telegram aceitava episódio inexistente.
- CI ficava em subpasta (e fora do repositório); agora está em `.github/` na raiz.
- Restaurados `.gitignore` e `.env.example`.

Novidades:
- Dicionário `[pronuncia]` e campo `pronuncia` por cena (só para a voz).
- `licencas.csv` por episódio; `--live` bloqueia mídia externa sem licença ou com NC/ND.
- Referências e créditos entram na descrição por código; `--publicar-em` é validado.
- Trava de tema repetido (`--forcar` para ignorar).
- Provedor de voz opcional `edge` (NOT_RUN).
- 50 testes offline.

## 0.1.0 — 2026-11-26 (protótipo)
- Pipeline completo pauta → roteiro → storyboard → gate humano → imagens → narração → render → publicação (DRY_RUN).
- Camada de LLM portátil com fallback, circuit breaker, cache e orçamento.
- Validação determinística de roteiro e de referências bíblicas (66 livros).
- Storyboard por regras de enquadramento com explicação por cena e ficha de personagens.
- Aprovação selada por SHA-256; ajuste humano vira feedback; Telegram opcional.
- Render ffmpeg com movimento por plano, legenda embutida e thumbnail.
- Observabilidade (run_id, eventos JSONL/SQLite, run_summary, explain, doctor) e documentação SDD/handoff.
- 34 testes offline + CI no GitHub Actions.
