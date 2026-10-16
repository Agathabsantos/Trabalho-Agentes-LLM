# Grafo, estado e conferência

O desenho canônico, as tabelas de nós/campos e a saída de `get_graph()` estão
em [arquitetura.md](arquitetura.md). Este documento registra a implementação e
os limites próprios do framework.

## Implementação

- `create_graph()` registra cinco nós e arestas condicionais em
  [src/graph.py](../src/graph.py#L234-L518).
- `get_graph()` compila o objeto uma vez, configura `SqliteSaver` e o mantém
  aberto para o CLI em [src/graph.py](../src/graph.py#L522-L527).
  [conferir_grafo.py](../conferir_grafo.py) importa `get_graph()`; não cria
  topologia paralela.
- O `interrupt()` e a retomada por `Command(resume=...)` estão em
  [src/graph.py](../src/graph.py#L434) e [src/graph.py](../src/graph.py#L555).
- Arestas condicionais levam destinos explícitos: `triage` para busca ou fim;
  `propose` para aprovação ou fim; `approval` para escrita ou fim.
- Não há nós paralelos no grafo de produto. O controle de reducer é um teste
  de duas branches em paralelo porque a entrega exige entender o comportamento.

## Padrões e autonomia

A combinação usada é sequência com portão + router; os padrões paralelos,
orquestrador-trabalhador, avaliador-otimizador e agente de laço não são usados.
Tabela e justificativas completas estão em `docs/arquitetura.md`. O degrau mais
caro (laço livre) foi rejeitado: uma interpretação tipada, uma consulta e uma
confirmação são suficientes; nenhuma resposta de ferramenta solicita outra
ferramenta escolhida pelo modelo.

## Reducers e teste sem reducer

`messages` usa `add_messages`; `evidence` e `trajectory` acumulam lista com
`list.__add__`. São canais que recebem atualizações de mais de um nó ao longo da
execução. Escalares (rota, decisão, título) têm um único escritor ativo por
ramo. O grafo de produto não tem corrida paralela.

No controle [paralelo](../tests/test_graph.py#L241), as duas branches atualizam `values`: com `operator.add`, a saída é
`["left", "right"]` (ordem não é contrato). Sem reducer, LangGraph 0.6.10
levanta `InvalidUpdateError` em vez de escolher o último nó. A implementação
não simula perda silenciosa onde o runtime realmente gera erro.

## O que o framework não fornece

- **Motivo do término:** `decision.status` e `trajectory` são definidos pelo
  projeto, não por `END`.
- **Detector de laço:** não existe laço de agente; `recursion_limit=12` é teto
  de segurança, não detector de repetição. Uma execução superior ao teto sobe
  erro de runtime.
- **Orçamento:** LangGraph fornece o limite de recursão; timeout de chamada,
  limite de tokens, limite de evidências e prazo HITL são do código/config.
- **Erro recuperável/fatal:** JSON do modelo vira recusa segura registrada;
  banco inacessível é fatal e sobe ao chamador.
- **Persistência e retomada:** checkpointer SqliteSaver do framework armazena o
  estado; o código define caminho, `thread_id`, política de retomada e idempotência.

**Framework cobre, sem código local:** execução do grafo de estado e gravação/
restauração de checkpoint são de LangGraph + `SqliteSaver`; o teste de
[reinício e retomada](../tests/test_graph.py#L144) fecha/reabre o saver e retoma
o mesmo thread. Versões fixadas em [requirements.txt](../requirements.txt).

## Parâmetros com valor local explícito

`recursion_limit=12`, `temperature=0.2`, `max_tokens=300`, `timeout=20 s`,
`MAX_EVIDENCES=12` (implementado como `limite=12`) e `APPROVAL_TIMEOUT_SECONDS=86400`.
Os defaults de biblioteca podem mudar numa atualização; os valores são
passados explicitamente e a versão do LangGraph/checkpointer é fixada.
