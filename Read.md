# Biblr 0.2.0

Pipeline local para produzir videos educativos de narrativas biblicas, com revisao humana.
[Documentacao e comandos](video-biblico-pipeline/README.md)



O Biblr é um pipeline em Python para produzir vídeos educativos sobre narrativas bíblicas. Ele transforma uma pauta em roteiro e storyboard, pede revisão teológica humana e depois reúne imagens, narração e legendas em um MP4.
Estado atual
A versão 0.2.0 é um protótipo funcional. A demo offline foi executada duas vezes e gerou um MP4 com imagens de teste, áudio silencioso e legendas. O histórico da versão documenta 50 testes offline. A publicação usa DRY_RUN por padrão.

Ainda falta validar o fluxo com voz e imagens reais e conferir as integrações externas listadas no [handoff](video-biblico-pipeline/HANDOFF.md). O próximo piloto proposto é um trecho de Rute 1 com narração própria e imagens próprias ou licenciadas, sem contratar serviços.
Rodar a demo
No CMD do Windows, abra a pasta do repositório. Use Python 3.11 ou superior e mantenha FFmpeg e FFprobe no PATH. Se o Python no Windows não encontrar o fuso America/Sao_Paulo, instale tzdata no ambiente usado para rodar o projeto.
cd video-biblico-pipeline
python scripts\vbp.py demo
Continuar o projeto
1. [README do pipeline](video-biblico-pipeline/README.md) para requisitos, instalação e comandos.
2. [HANDOFF.md](video-biblico-pipeline/HANDOFF.md) para estado técnico, pendências e próximos passos.
3. [AGENTS.md](video-biblico-pipeline/AGENTS.md) antes de alterar o código. A revisão humana é obrigatória antes da geração de mídia e da publicação.
4. [Decisões técnicas](video-biblico-pipeline/docs/DECISIONS.md) e [changelog](video-biblico-pipeline/CHANGELOG.md) para entender as escolhas e o histórico.
Ao concluir uma mudança relevante, atualize o handoff com o que mudou, os testes realmente executados e as pendências.
