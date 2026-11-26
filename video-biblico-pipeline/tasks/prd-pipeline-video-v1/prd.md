# Documento de Requisitos do Produto (PRD) — Pipeline de Vídeo Bíblico v1

> **Status:** `DRAFT` — aguardando aprovação do owner. Aprovador: owner. Data: —

## Visão geral

Criadores evangélicos que querem produzir conteúdo educativo em vídeo não têm tempo nem equipe para roteirizar,
ilustrar, narrar e editar vídeos longos com qualidade. Fábricas de vídeo por IA resolvem o volume, mas produzem
conteúdo genérico, emocionalmente manipulador e teologicamente impreciso — que o YouTube desmonetiza e o público rejeita.

O pipeline transforma uma pauta (título, tema, referências) em um vídeo educativo pronto (roteiro fiel, storyboard
cinematográfico, imagens, narração, legendas, thumbnail), com **revisão humana obrigatória** e custo controlado,
servindo como topo de funil para produtos de ticket alto (ver `docs/STRATEGY.md`).

## Objetivos

- **OBJ-1:** produzir 3–4 vídeos/semana com no máximo 3 h de trabalho humano por vídeo (revisão + ajustes).
- **OBJ-2:** 100% dos vídeos publicados com aprovação humana registrada e válida.
- **OBJ-3:** custo variável por vídeo ≤ R$ 10 (meta do orçamento de R$100–500/mês).
- **OBJ-4:** zero vídeo com isca emocional ou referência bíblica inexistente (validador + revisão).
- **OBJ-5:** qualquer execução explicável a posteriori (o que foi feito, por quê, com que custo).

## Histórias de usuário

- US1: Como produtor, quero importar uma pauta e obter roteiros validados para revisar, em vez de escrever do zero.
- US2: Como revisor, quero ler um resumo e o roteiro completo e aprovar ou pedir ajuste com um motivo.
- US3: Como produtor, quero que nada seja renderizado ou publicado sem minha aprovação.
- US4: Como produtor, quero que o vídeo tenha enquadramentos variados e coerentes com a narrativa.
- US5: Como produtor, quero gerar imagens e voz com ferramentas locais ou externas, sem ficar preso a um fornecedor.
- US6: Como produtor, quero retomar de onde parei sem pagar de novo pelo que já foi feito.
- US7: Como owner, quero saber quanto cada execução custou e por que algo falhou.
- US8 (secundária): Como revisor, quero aprovar pelo celular (Telegram).

## Principais funcionalidades

- **Roteiro:** RF1 gerar roteiro estruturado (gancho, 6–8 seções, conclusão, título, texto de thumbnail, descrição);
  RF2 validar formato, referências (livro/capítulo), frases proibidas e duração; RF3 regenerar com feedback, limitado.
- **Storyboard:** RF4 dividir em cenas; RF5 escolher enquadramento por regras explicáveis; RF6 manter personagens consistentes.
- **Revisão:** RF7 gate de aprovação selado por conteúdo; RF8 pedido de ajuste realimenta o roteiro; RF9 canal Telegram.
- **Mídia:** RF10 imagens por provedor plugável; RF11 narração por cena; RF12 render com movimento por plano,
  legendas e thumbnail.
- **Publicação:** RF13 DRY_RUN por padrão; RF14 upload privado/agendado só com `--live` e aprovação válida.
- **Operação:** RF15 estado persistente e idempotente; RF16 orçamento por execução; RF17 logs, métricas e explicações.

## Critérios de aceitação

- CA-01 (RF1–RF2): dado um roteiro sem referência em alguma seção, quando validado, então é reprovado indicando a seção.
- CA-02 (RF2): dado um roteiro com frase de isca ("não pule este vídeo"), quando validado, então é reprovado.
- CA-03 (RF3): dado um LLM que erra o formato, quando a etapa roda, então há no máximo 2 tentativas, a 2ª com feedback, e depois BLOCKED com diagnóstico.
- CA-04 (RF5): cada cena do storyboard registra plano, regra e palavra-gatilho; não há 3 planos iguais seguidos.
- CA-05 (RF6): cena que cita um personagem da ficha usa a descrição e a seed fixas dele.
- CA-06 (RF7, US3): sem aprovação, a execução para antes de IMAGENS.
- CA-07 (RF7): alterar roteiro/storyboard após aprovação invalida a aprovação.
- CA-08 (RF8): pedido de ajuste aparece no prompt da nova versão do roteiro.
- CA-09 (RF12): o vídeo final contém faixas de vídeo, áudio e legenda; thumbnail e SRT existem.
- CA-10 (RF13–RF14): sem `--live`, nada é enviado; com `--live` e sem aprovação, a publicação é bloqueada.
- CA-11 (RF15): segunda execução sem mudanças não chama o LLM.
- CA-12 (RF16): orçamento estourado gera BLOCKED com diagnóstico, sem chamar o provedor.
- CA-13 (RF17): todo evento tem run_id; segredos não aparecem em logs.

## Experiência do usuário

Operação por CLI em português, com mensagens de status curtas (PASS/BLOCKED/…) e arquivos legíveis por humanos
(`roteiro.md`, `REVISAO.txt`). Revisão também pelo Telegram. Sem interface web na v1.

## Restrições técnicas de alto nível

- Rodar na máquina do owner (Windows/macOS/Linux), Python ≥ 3.11 e ffmpeg.
- Integrações: provedores de LLM (local e nuvem), geradores de imagem/voz, YouTube Data API, Telegram Bot API.
- Segredos fora do Git. Conteúdo gerado deve declarar mídia sintética ao YouTube.
- Respeitar direitos autorais de traduções bíblicas (paráfrase + referência; citações curtas).

## Fora do escopo

- Geração de vídeo por modelos de vídeo (só imagem + movimento de câmera na v1).
- Interface web/app, multiusuário, edição manual dentro da ferramenta.
- Bot de devocional, página de captura e produto de coprodução (projetos irmãos).
- Publicação em outras plataformas (TikTok/Instagram) na v1.
