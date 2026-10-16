# Estado da entrega — Parte 2

Atualizado em 2026-10-16. A Parte 1 e mantida como baseline nos arquivos
`src/agent.py`, `src/motores.py`, `src/verificador.py` e nos logs originais.

## Itens consolidados

| Frente | Artefato/implementação | Estado honesto |
|---|---|---|
| Complemento do case | `docs/case.md` §10–12 | feito; descreve exceções, vocabulário, limites do fixture |
| Entrada/saída | `src/graph.py`, `docs/io.md` | texto livre, metadados separados, saída Pydantic |
| Prompt | `src/prompts/`, `docs/prompts.md` | versão/hash em log; teste A/B real do provedor pendente |
| Arquitetura/grafo/estado | `docs/arquitetura.md`, `docs/grafo.md`, `conferir_grafo.py` | LangGraph executável, topologia conferida |
| RAG | `src/rag.py`, `dados/rag_corpus.jsonl`, `dados/rag_eval.json`, `docs/rag.md` | busca textual + SQL; não vetorial; corpus sintético |
| Memória | SQLite histórico/episódios/opt-in, checkpointer SQLite; `docs/memoria.md` | código e testes; exclusão por titular não implementada no protótipo sintético |
| HITL | `interrupt`, `Command(resume)`, chave idempotente; `docs/humano.md` | pausa/edição/rejeição/expiração no resume testadas; aprovador é simulado |
| Casos | `logs/part2_runs.json` | nove execuções locais, zero chamadas LLM; metadado indica árvore suja |
| Projeto | README, requirements, `.env.example`, `.gitignore` | instruções e versões fixadas |

## Verificação

A última execução no ambiente Python 3.13.5 validou 18 testes. O log de demo
foi produzido por `python src/demo_part2.py`; a topologia por
`python conferir_grafo.py`. Os logs carimbam `engine=regras_locais` e
`model_calls=0` porque não havia chave de API. Isso demonstra execução real do
grafo, não qualidade de saída do LLM.

## Pendências externas ao código desta sessão

1. Depois do commit consolidado do grupo, rodar `python src/demo_part2.py`
   novamente para gravar SHA limpo; os logs atuais registram o commit pai e
   `working_tree_dirty=true` de forma explícita.
2. Com credencial do provedor, comparar o prompt com e sem a frase de segurança
   em `docs/prompts.md` e gravar os resultados rotulados, custo e validade.
3. Obter/autorizar corpus externo e disponibilidade real antes de alegar
   cobertura de catálogo de produção.
4. Se houver usuário real, adicionar autenticação, serviço de expiração e
   remoção verificável de checkpoint/log/backup, não só das tabelas SQLite.

Não são alegações de qualidade produzidas nesta entrega: resultado novo do LLM,
benchmark de embeddings, teste de carga, disponibilidade atual de streaming ou
conformidade operacional LGPD.
