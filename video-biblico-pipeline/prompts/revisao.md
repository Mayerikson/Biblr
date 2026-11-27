# Checklist de revisão humana (etapa de aprovação)

A máquina valida formato, referências (livro/capítulo) e frases proibidas. Só uma pessoa valida fidelidade.
Antes de aprovar um episódio, confira:

- [ ] Cada afirmação "a Bíblia diz" confere com a passagem citada (abra a Bíblia e leia).
- [ ] Nenhuma fala foi atribuída a personagem bíblico sem base no texto.
- [ ] Contexto histórico/arqueológico está apresentado como contexto, não como texto bíblico.
- [ ] Interpretações doutrinárias disputadas estão neutras ou fora do roteiro.
- [ ] Nada de isca emocional, promessa de cura/prosperidade ou ataque a outras denominações.
- [ ] Citações literais curtas (≤ 25 palavras) e tradução identificada quando houver.
- [ ] Storyboard: imagens respeitosas, sem violência gráfica, sem anacronismos.
- [ ] Nomes bíblicos soam certos na narração; imagens e músicas externas têm licença registrada.
- [ ] Título e thumbnail honestos (curiosidade, não mentira).

Aprovar: `python scripts/vbp.py approve EP001 --por "Seu Nome"`
Pedir ajuste: `python scripts/vbp.py reject EP001 --motivo "Seção 3 atribui fala a Davi sem referência"`
