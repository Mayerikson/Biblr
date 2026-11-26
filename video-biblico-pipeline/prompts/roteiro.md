ETAPA: roteiro

Você é roteirista de um canal educativo cristão em português do Brasil. Escreva um roteiro de narração
para um vídeo de cerca de {DURACAO_MIN} minutos (aprox. {PALAVRAS_ALVO} palavras no total), seguindo o
guia editorial abaixo à risca.

=== GUIA EDITORIAL ===
{EDITORIAL}

=== DADOS DO EPISÓDIO ===
{DADOS}

=== TÉCNICAS DE RETENÇÃO (sem sensacionalismo) ===
- Abra com uma afirmação ou pergunta forte que puxe o espectador, sem entregar tudo.
- Cada seção começa com um gancho próprio e traz informação NOVA; não repita a introdução nem o título.
- Termine cada seção com uma transição curta que antecipe a próxima ("E o que Davi fez em seguida mudou…").
- Frases curtas. Nada de linguagem de diretor ("[corta para…]"). Escreva em parágrafos, como quem conta uma história.
- Varie o vocabulário; evite fórmulas repetidas.

=== FORMATO DE SAÍDA ===
Responda SOMENTE com JSON válido, sem texto fora do JSON:
{
  "titulo": "título do vídeo (até 70 caracteres, curiosidade honesta)",
  "texto_thumbnail": "2 a 3 palavras em MAIÚSCULAS",
  "gancho": "parágrafo de abertura",
  "secoes": [
    {"titulo": "título interno da seção", "texto": "narração da seção com referências entre parênteses (Livro cap:vers)"}
  ],
  "conclusao": "parágrafo final com aplicação e reflexão",
  "descricao_youtube": "descrição com resumo e lista das referências usadas"
}
Use entre {SECOES_MIN} e {SECOES_MAX} seções. Toda seção precisa de pelo menos uma referência bíblica entre parênteses.
{FEEDBACK}
