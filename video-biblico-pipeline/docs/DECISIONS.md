# Raciocínio documentado — Registro de Decisões (ADRs)

Formato MYK: **contexto → opções → decisão → justificativa → evidências → trade-offs → risco → aprovador**.
Isto é a "cadeia de pensamento" do projeto em forma auditável: o porquê de cada escolha, as alternativas descartadas
e o que mudaria a decisão. Status: `PROPOSTA` (aguarda owner), `ACEITA`, `SUBSTITUÍDA`.

---

## ADR-001 — Nicho: canal educativo de narrativas bíblicas em vídeo longo
- **Contexto:** owner quer renda com conteúdo automatizado; 5–15 h/semana; R$100–500/mês; programador; evangélico.
- **Opções:** (a) Shorts virais para AdSense; (b) devocional genérico ("mensagem do dia"); (c) filosofia/mente estilo estudo de caso; (d) educativo bíblico longo (contexto, personagens, geografia).
- **Decisão:** (d).
- **Justificativa:** (a) paga ~R$0,03/mil views (caso real: 30M views → R$885) e é o formato mais visado pela política de conteúdo inautêntico; (b) é o terreno mais saturado de isca emocional, que o YouTube desmonetiza; (c) não usa a vantagem do owner; (d) une público grande, pouca concorrência de qualidade, vídeo longo (RPM maior) e a capacidade do owner de validar a teologia.
- **Evidências:** `docs/RESEARCH.md` (política jul/2026, encerramentos jan/2026, Censo 2022).
- **Trade-offs:** produção mais trabalhosa que Shorts; RPM em português menor que em inglês.
- **Risco:** depender de AdSense; mitigado pela ADR-002.
- **Aprovador:** owner — `PROPOSTA` (escolha feita na conversa; formalizar).

## ADR-002 — Modelo de negócio híbrido: canal = funil; coprodução = receita principal
- **Contexto:** "conteúdo bom só monetiza por conexão ou por nicho de ticket alto".
- **Opções:** AdSense puro; afiliados; serviço de automação para igrejas; coprodução de formação (pastores/líderes).
- **Decisão:** canal e bot como topo de funil; validar coprodução (formação prática para pastores/líderes) e serviço para igrejas; AdSense/afiliados como bônus.
- **Justificativa:** uma venda de ticket alto equivale a dezenas de milhões de views em Shorts; coprodução resolve a **Autoridade** (tríade A.E.I.) com um especialista real; o owner entra com o que sabe (automação, funil, conteúdo em escala).
- **Trade-offs:** depende de encontrar coprodutor confiável; exige validação com pastores antes de construir.
- **Risco:** produto doutrinariamente divisivo → focar em habilidades práticas ou numa tradição específica.
- **Aprovador:** owner — `PROPOSTA` (pendente de entrevistas de validação).

## ADR-003 — Local-first e model-portable
- **Opções:** SDK de um fornecedor; API compatível com OpenAI + adaptadores.
- **Decisão:** `openai_compat` (Ollama, LM Studio, Groq, OpenRouter) + `gemini`, em cadeia de fallback configurável.
- **Justificativa:** custo perto de zero com modelo local; troca de fornecedor só no TOML; padrão já usado no Fitness-Manager e no jobs-engine.
- **Trade-offs:** modelo local menor escreve pior → compensado por validação + revisão humana.
- **Aprovador:** owner — `PROPOSTA`.

## ADR-004 — Storyboard por regras determinísticas; LLM só descreve
- **Opções:** LLM escolhe tudo; regras escolhem o plano e o LLM descreve; só regras.
- **Decisão:** regras (`SHOT_RULES`) escolhem o plano com restrição de variedade; LLM opcional descreve a composição e **não pode** trocar o plano.
- **Justificativa:** custo zero, previsível, explicável (cada cena registra regra + palavra-gatilho), testável; o material de storyboard do owner vira código.
- **Trade-offs:** regras por palavra-chave erram nuances → ajuste fino no TOML/código e na revisão humana.
- **Evidências:** testes `test_regra_de_plano_e_explicacao`, `test_restricao_de_variedade`, `test_llm_nao_muda_plano`.
- **Aprovador:** owner — `PROPOSTA`.

## ADR-005 — Gate humano com aprovação selada por hash
- **Decisão:** nada de imagens/render/publicação sem aprovação; a aprovação grava SHA-256 de roteiro+storyboard; qualquer mudança invalida; publicação verifica de novo (defesa em profundidade).
- **Justificativa:** é o que diferencia de fábrica de slop (política do YouTube exige valor/criação humana) e protege contra erro teológico — o maior risco reputacional no nicho.
- **Evidências:** `test_alterar_conteudo_invalida_aprovacao`, `test_publicacao_live_nunca_sem_aprovacao`.
- **Trade-offs:** exige tempo do owner por episódio (mitigado por `REVISAO.txt`, checklist e Telegram).
- **Aprovador:** owner — `PROPOSTA`.

## ADR-006 — Agendar com o próprio YouTube (publishAt), sem servidor
- **Opções:** cron no GitHub Actions (como o jobs-engine); servidor; agendamento nativo do YouTube.
- **Decisão:** render e upload rodam na máquina do owner; o vídeo sobe privado com `publishAt`.
- **Justificativa:** runners padrão do Actions não têm GPU (geração de imagem local) e vídeos são grandes para o Git; o YouTube já agenda de graça. Actions fica com CI.
- **Trade-offs:** a máquina precisa estar ligada no momento do upload (não da publicação).
- **Aprovador:** owner — `PROPOSTA`.

## ADR-007 — SQLite com eventos append-only, idempotência por hash e cache de LLM
- **Decisão:** estado em SQLite; `events` protegido por triggers; cada etapa guarda o hash das entradas e é pulada se nada mudou; respostas de LLM em cache por hash do prompt.
- **Justificativa:** retomar de onde parou, auditar tudo, nunca pagar duas vezes pelo mesmo prompt (2ª execução da demo: 0 chamadas de LLM — medido nos testes).
- **Aprovador:** owner — `PROPOSTA`.

## ADR-008 — Referências bíblicas fora da fala e da legenda
- **Decisão:** o roteiro exige "(Livro cap:vers)" para validação; a narração/legenda remove os parênteses; as referências ficam na descrição e no storyboard.
- **Justificativa:** ler "primeiro Samuel dezessete quarenta e cinco" quebra o ritmo; a fidelidade continua rastreável.
- **Alternativa futura:** citar oralmente só as referências-chave ("como está em 1 Samuel 17").
- **Aprovador:** owner — `PROPOSTA`.

## ADR-009 — Narração por cena; legendas determinísticas
- **Decisão:** um áudio por cena; a duração do clipe = duração do áudio; SRT gerado proporcionalmente às palavras.
- **Justificativa:** sincronia por construção, sem Whisper/alinhamento forçado; reprocessa só a cena alterada.
- **Trade-offs:** micro-desalinhamento dentro da cena (aceitável); Whisper fica como melhoria opcional.
- **Aprovador:** owner — `PROPOSTA`.

## ADR-010 — Orçamento explícito por execução (bounded efficiency)
- **Decisão:** limites de chamadas, tokens estimados, custo, tentativas (2), cenas e tempo; estourou → `BLOCKED` + `diagnostico_<etapa>.json`.
- **Justificativa:** evitar loops caros e silenciosos; "após repetição, diagnostique" (padrão MYK).
- **Aprovador:** owner — `PROPOSTA`.

## ADR-011 — O que NÃO copiar do estudo de caso "0 aos 5 dígitos"
- **Contexto:** o material recomenda copiar um canal que atribui a autoridades frases provavelmente inventadas, usa prompt de canal de fofoca ("rumores, controvérsias, especulações") e ensina a "censurar" palavras para driblar diretrizes.
- **Decisão:** manter formato (vídeo longo, imagem + narração, thumbnail com 2–3 palavras, estrutura de retenção); proibir atribuições sem fonte, isca emocional e drible de filtros (validador `BANNED` + `prompts/editorial.md`).
- **Justificativa:** no nicho evangélico, palavra inventada na boca de personagem bíblico é falso testemunho e destrói a confiança; drible de diretriz pesa quando o YouTube revisa o canal inteiro.
- **Aprovador:** owner — `PROPOSTA`.

## ADR-012 — Transparência sobre IA e privacidade padrão
- **Decisão:** upload sempre `private` (ou agendado) e `containsSyntheticMedia=true`.
- **Justificativa:** honestidade com o público e conformidade com regras de divulgação de mídia sintética. (Confirmar o campo na API — NOT_RUN.)
- **Aprovador:** owner — `PROPOSTA`.

## ADR-013 — Python stdlib-first, sem orquestradores pesados
- **Decisão:** núcleo sem dependências; Pillow e Google API opcionais; nada de Airflow/Kafka/runtime de agentes.
- **Justificativa:** roda em qualquer máquina, fácil de manter sozinho, fácil de outra IA entender.
- **Aprovador:** owner — `PROPOSTA`.
