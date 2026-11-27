# Runbook — operação e problemas comuns

## Rotina semanal sugerida (5–15 h)
1. Atualizar a pauta (`data/pauta.csv`) e `import-pauta`.
2. `run` para gerar roteiros/storyboards (param no gate).
3. Revisar com `prompts/revisao.md` → `approve` ou `reject --motivo`.
4. `run` de novo para imagens, narração e render. Assistir ao vídeo inteiro antes de publicar.
5. `run -e EPxxx --live --publicar-em 2026-12-05T21:00:00Z` (sobe privado e agendado).
6. `report` e anotar o que aprendeu.

## Licenças (mídia sua ou de terceiros)
Crie `workspace/episodios/EPxxx/licencas.csv` (aceita curinga):
```csv
arquivo,autor,licenca,origem
audio/*,Seu Nome,gravação própria,
imagens/cena_001.png,Nome do autor,CC BY 4.0,https://link-da-imagem
```

## Antes do primeiro `--live`
- Confira a auditoria do projeto no Google: sem ela os envios podem ficar presos como privados. Teste com um vídeo.
- App OAuth em modo "Teste" expira a autorização a cada 7 dias (relato do livro Framework Antares; confirme).

## Problemas
| Sintoma | Onde olhar | Ação |
|---|---|---|
| ROTEIRO `BLOCKED` "reprovado na validação" | `diagnostico_roteiro.json`, `roteiro.rejeitado.json` | ajustar prompt/modelo; checks mostram exatamente o que falhou |
| ROTEIRO `BLOCKED` "LLM indisponível" | eventos `llm_failure` | Ollama ligado? chave no .env? `doctor` |
| `BLOCKED` "orçamento estourado" | `diagnostico_*.json` → `orcamento` | entender o porquê antes de aumentar o limite |
| APROVACAO `BLOCKED` | `REVISAO.txt` | é esperado: revise e aprove |
| "conteúdo mudou depois da aprovação" | `vbp explain` | alguém editou roteiro/storyboard: revise de novo |
| IMAGENS `BLOCKED` (externo) | `imagens/prompts.json` | gere as imagens e salve como `cena_NNN.png` |
| RENDER falhou | stderr do ffmpeg no motivo | `doctor`; confira imagens corrompidas/áudio vazio |
| Quero refazer uma cena | apague `imagens/cena_NNN.png` ou `audio/cena_NNN.wav` | `run` refaz só ela |
| Pronúncia errada | `[pronuncia]` no TOML | adicione a palavra e rode de novo; a legenda não muda |
| "tema repetido" ao importar | `vbp status` | mude a pauta ou use `--forcar` |
| `--live` BLOCKED "licenças pendentes" | `licencas.csv` | registre autor e licença |
| Quero refazer o roteiro do zero | `reject --motivo "..."` | o próximo `run` regenera com o pedido |
