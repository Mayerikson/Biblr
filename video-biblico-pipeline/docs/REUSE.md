# Reaproveitamento dos outros repositórios do owner

| Origem | Padrão | Onde está aqui |
|---|---|---|
| digisystem-jobs-engine | coletar → planejar → redigir em lotes → validar → publicar | `vbp/pipeline.py` (pauta → roteiro → storyboard → … → publicação) |
| digisystem-jobs-engine | prompt editorial separado do código (`prompt_pronto.txt`) | `prompts/editorial.md`, `prompts/roteiro.md` |
| digisystem-jobs-engine | validação determinística + regeneração limitada + diagnóstico | `vbp/script.py::validate_script`, `Pipeline.stage_script` |
| digisystem-jobs-engine | Gemini → Groq com circuit breaker, controle de orçamento | `vbp/llm.py::LLMClient`, `vbp/budget.py` |
| digisystem-jobs-engine | `DRY_RUN` como padrão; persistir estado antes de publicar | `--live` explícito; `publish_plan.json`; SQLite |
| digisystem-jobs-engine | `run_summary.json` por execução | `vbp/obs.py::Observer.summary` |
| Fitness-Manager | Telegram com allowlist, confirmação antes de gravar, offset persistido | `vbp/approval.py::Telegram` |
| Fitness-Manager | adaptador de LLM local compatível com OpenAI (Ollama/LM Studio) | `vbp/llm.py::OpenAICompat` |
| Fitness-Manager | SQLite append-only, idempotência por chave | `vbp/state.py` (triggers + hashes) |
| Fitness-Manager | "LLM interpreta, Python calcula"; confirmação humana | ADR-004, ADR-005 |
| Fitness-Manager | faster-whisper local | sugestão futura (legendas por transcrição) |
| Spec (SDD/MYK) | PRD → TechSpec → tasks → QA → review; IDs rastreáveis; PASS/FAIL/BLOCKED/NOT_RUN | `tasks/prd-pipeline-video-v1/`, `AGENTS.md`, `HANDOFF.md` |
| Spec (MYK) | Bounded Efficiency, Explainability & Observability, ADRs | `docs/EFFICIENCY.md`, `docs/OBSERVABILITY.md`, `docs/DECISIONS.md` |

Também serve de **portfólio**: na conversa com coprodutores ou igrejas, os três repositórios mostram que o owner já
construiu sistemas que coletam, geram, validam e publicam sozinhos.
