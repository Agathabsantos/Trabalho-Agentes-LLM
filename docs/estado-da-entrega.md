# Estado da entrega — Parte 2

Atualizado em 2026-10-17. A Parte 1 e mantida como baseline nos arquivos
`src/agent.py`, `src/motores.py`, `src/verificador.py` e nos logs originais.

## Itens consolidados

| Frente | Artefato/implementação | Estado honesto |
|---|---|---|
| Complemento do case | `docs/case.md` §10–12 | feito; descreve exceções, vocabulário, limites do fixture |
| Entrada/saída | `src/graph.py`, `docs/io.md` | texto livre, metadados separados, saída Pydantic |
| Prompt | `src/prompts/`, `docs/prompts.md`, `src/ab_frase.py` | `interpret_request.txt` v2 (few-shot), que corrigiu o JSON inválido da v1 com o modelo; versão/hash em log; A/B da frase rodado (90 chamadas), a frase fica |
| Arquitetura/grafo/estado | `docs/arquitetura.md`, `docs/grafo.md`, `conferir_grafo.py` | LangGraph executável, topologia conferida |
| RAG | `src/rag.py`, `dados/rag_corpus.jsonl`, `dados/rag_eval.json`, `docs/rag.md` | busca textual + SQL; não vetorial; corpus sintético |
| Memória | SQLite histórico/episódios/opt-in, checkpointer SQLite; `docs/memoria.md` | código e testes; remoção por titular (`src/remover_titular.py`) com varredura e teste; decaimento não implementado, com justificativa |
| HITL | `interrupt`, `Command(resume)`, chave idempotente, `src/expirar_pendencias.py`; `docs/humano.md` | pausa/edição/rejeição/expiração testadas, inclusive a varredura do agendador; aprovador é simulado |
| Casos | `logs/part2_runs.json` | nove execuções com o modelo, árvore limpa; 8 de 9 com o status esperado, o caso 01 falha por interpretação do modelo |
| Projeto | README, requirements, `.env.example`, `.gitignore` | instruções e versões fixadas |

## Verificação

A última execução (Python 3.14.7, 2026-10-17) validou 20 testes, que rodam sem
modelo mesmo com chave no `.env`. A demo
(`python src/demo_part2.py`) rodou com `ministral-8b-2512` no commit `6c3ebf4`,
com `working_tree_dirty=false`; o A/B da frase rodou no commit `1d421e1`; a
topologia foi conferida por `python conferir_grafo.py`.

## Pendências externas ao código desta sessão

1. Se o modelo mudar, rodar de novo a demo e o A/B depois de commitar, e
   atualizar `docs/io.md`, `README.md` e `docs/prompts.md` com o log novo.
2. Agendar `python src/expirar_pendencias.py` de hora em hora (cron) na máquina
   que hospeda o sistema; a rotina e o teste existem, o agendamento não é do
   repositório.
3. Obter/autorizar corpus externo e disponibilidade real antes de alegar
   cobertura de catálogo de produção.
4. Se houver usuário real, adicionar autenticação e estender a remoção a
   backups e aos logs versionados; hoje o script só aponta em quais logs o id
   aparece.

Não são alegações de qualidade produzidas nesta entrega: qualidade do LLM além
dos 9 casos e 90 chamadas registrados,
benchmark de embeddings, teste de carga, disponibilidade atual de streaming ou
conformidade operacional LGPD.
