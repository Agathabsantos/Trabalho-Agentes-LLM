# Fontes consultadas

## Documentação técnica

| Fonte | Link | Uso/limite |
|---|---|---|
| LangGraph — Graph API | https://docs.langchain.com/oss/python/langgraph/graph-api | `StateGraph`, estado, reducers, nós, arestas condicionais, `recursion_limit`; versão local fixada em 0.6.10 |
| LangGraph — Interrupts | https://docs.langchain.com/oss/python/langgraph/interrupts | `interrupt`, reinício do nó, `Command(resume=...)`, necessidade de checkpoint e idempotência |
| LangGraph — Persistence | https://docs.langchain.com/oss/python/langgraph/persistence | fronteira checkpointer/thread vs armazenamento de longo prazo; implementação usa SQLite local |
| LangGraph — Add memory | https://docs.langchain.com/oss/python/langgraph/add-memory | conceito de memória curta/longa; o projeto guarda episódica e chave-valor no próprio SQLite |
| LangGraph API, `SqliteSaver` | https://reference.langchain.com/python/langgraph/checkpoints/ | checkpointer e retomada; `langgraph-checkpoint-sqlite==2.0.11` |
| SQLite FTS5 | https://www.sqlite.org/fts5.html | busca textual, `MATCH`, BM25/ordenação; índice de episódios da memória |
| SQLite | https://www.sqlite.org/docs.html | transações e consultas das tabelas do catálogo/histórico |
| Python `sqlite3` | https://docs.python.org/3/library/sqlite3.html | camada de persistência e `BEGIN IMMEDIATE` |
| Python `unicodedata` | https://docs.python.org/3/library/unicodedata.html | normalização de acentos |
| Pydantic models | https://pydantic.dev/docs/validation/latest/concepts/models/ | validar `RecommendationResult` e `Interpretation` |
| OpenAI Chat Completions | https://platform.openai.com/docs/api-reference/chat | chamada compatível de interpretação quando há credencial; modo local não representa resultado de LLM |
| OpenAI JSON mode / structured output | https://platform.openai.com/docs/guides/structured-outputs | formato JSON; validação semântica local continua necessária |
| Python `hashlib` | https://docs.python.org/3/library/hashlib.html | SHA-256 do prompt e chave de idempotência derivada de JSON canônico |
| Python `json` | https://docs.python.org/3/library/json.html | schema e logs JSON versionados |
| Mistral AI — Docs | https://docs.mistral.ai/ | endpoint compatível configurável; nenhum serviço externo consultado durante as demos |
| Mistral API Pricing | https://mistral.ai/pricing/api | preços usados no benchmark da Parte 1, consultados em 2026-09-18 |
| Mistral pricing docs | https://docs.mistral.ai/inference/pricing | segunda conferência dos preços da Parte 1 |

## Enunciado e material da disciplina

- Enunciado da Parte 2 (“O agente de verdade”), fornecido pelo usuário nesta conversa: onze itens, contrato de I/O, RAG, memória, LangGraph e HITL.
- Visão geral do trabalho e enunciado da Parte 1, registrados na documentação inicial do projeto.
- Aulas 05–09: padrões de workflow, reducers, checkpoint, interrupção e LangGraph; decisões contextualizadas em `docs/arquitetura.md` e `docs/grafo.md`.
- Aula 03: versionamento de prompt e hipótese de remoção documentada em `docs/prompts.md`.
- Caso Klarna, visto em aula, usado na análise anterior da tensão negócio/usuário em `docs/case.md`.

## Dados e domínio

`dados/streaming_catalog.json`, `dados/historico_seed.jsonl` e as avaliações em
`dados/rag_corpus.jsonl` são dados **sintéticos escritos para o exercício**.
Nomes de obras são reais; tags, reviews, plataformas, disponibilidade e
classificações não são verificados e não devem ser atribuídos a serviços atuais.
A demo não consultou TMDB, IMDb, JustWatch nem APIs de streaming. A decisão de
buscar lexicalmente e os dez casos de avaliação estão em `docs/rag.md` e
`dados/rag_eval.json`.

## Não consultado/não implementado

- Não há servidor/cliente MCP nesta Parte 2, embora o enunciado sugira MCP como ecossistema possível.
- Não há base vetorial, modelo de embeddings, API de catálogo externa ou medição de paralelismo.
- Não foi executado teste A/B real de remoção de frase no provedor: não havia `.env`/credencial na sessão. O documento de prompt declara essa limitação, não finge resultado.
