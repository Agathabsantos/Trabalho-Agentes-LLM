# Avaliação da Parte 2 — resultados reproduzíveis e limites

> Este arquivo substitui o plano de avaliação escrito antes do grafo. As
> afirmações abaixo descrevem apenas testes efetivamente executados em
> 2026-10-16; o planejamento antigo de 19 casos, juiz LLM e teste ao vivo de
> TMDB não foi uma execução e não é levado adiante como resultado.

## Suíte executável

- `tests/test_graph.py` e `tests/test_authority_controls.py`: **18 testes**
  unitários/integrados.
- Cobertura funcional: contrato e rota de recusa, título de referência ausente
  com contorno pelo clima explícito, filtros, evidência revogada, reducers,
  checkpoint reiniciado, pausa, edição, rejeição, prazo e idempotência.
- `dados/rag_eval.json`: 10 perguntas e formas apropriadas de recuperar; o
  arquivo classifica perguntas e identifica fontes, não é um benchmark
  estatístico de recall/precisão ainda.
- `logs/part2_runs.json`: 9 execuções do grafo, sem chave de API, executadas
  pelo parser local e com aprovações simuladas. O commit-base e estado sujo
  estão explicitamente registrados.

## Resultado que os testes suportam

A suíte confirma que os invariantes de código barram elegibilidade inválida;
uma recomendação exige trecho ativo do corpus; título de referência ausente
não induz substituição inventada; a pausa acontece antes da escrita; uma
retomada após reiniciar o saver mantém o thread; repetição com mesma chave não
cria segundo registro; rejeição/expiração não gravam. O teste de controle
paralelo mostra que LangGraph 0.6.10 combina listas com reducer e levanta
`InvalidUpdateError` quando branches atualizam o mesmo campo sem reducer.

**Não** há número medido de acerto do LLM nesta Parte 2: nenhum log novo chamou
modelo. `docs/modelos.md` e `logs/demo_runs.json` são baseline da Parte 1 em
cinco casos, não avaliação deste grafo. O parser local demonstra operação, mas
não representa desempenho semântico de um LLM. Não foram medidos recall@k,
precisão de citação em amostra humana, latência sob carga, custo do modelo novo
ou concordância de juiz.

## Critérios de próxima avaliação

1. Com provedor configurado, rotular previamente os casos; executar pelo menos
   10 repetições em temperatura de produção, mantendo snapshots de catálogo e
   prompt hash.
2. Medir rota/clima contra rótulo, elegibilidade e evidência separadamente;
   qualquer violação de assinatura/classificação/histórico reprova.
3. Para RAG, medir recall@12 e citação correta sobre os 10 itens de
   `rag_eval.json`; não contar pergunta sem resposta como falha do índice quando
   a saída esperada é recusa.
4. Validar a frase do `reason` por anotação humana antes de introduzir juiz LLM.
5. Fazer A/A antes de comparar prompt/modelo e atualizar a regra de promoção
   antes de olhar resultado.

A atual amostra de 9 casos é pequena, fixture autoral e não representativa de
usuários ou catálogo real. As limitações estão incorporadas a `docs/rag.md`,
`docs/prompts.md` e ao model card da Parte 1.
