# Grafo, estado e conferência

O desenho canônico, as tabelas de nós/campos e a saída de `get_graph()` estão
em [arquitetura.md](arquitetura.md). Este documento registra a implementação e
os limites próprios do framework.

## Implementação

- `create_graph()` registra cinco nós e arestas condicionais em
  [src/graph.py](../src/graph.py#L241-L527).
- `get_graph()` compila o objeto uma vez, configura `SqliteSaver` e o mantém
  aberto para o CLI em [src/graph.py](../src/graph.py#L531-L536).
  [conferir_grafo.py](../conferir_grafo.py) importa `get_graph()`; não cria
  topologia paralela.
- O `interrupt()` e a retomada por `Command(resume=...)` estão em
  [src/graph.py](../src/graph.py#L443) e [src/graph.py](../src/graph.py#L583).
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

No controle [paralelo](../tests/test_graph.py#L264), as duas branches atualizam `values`: com `operator.add`, a saída é
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
- **Erro recuperável/fatal:** falha ou JSON inválido do modelo termina com `status=error` registrado;
  banco inacessível é fatal e sobe ao chamador.
- **Persistência e retomada:** checkpointer SqliteSaver do framework armazena o
  estado; o código define caminho, `thread_id`, política de retomada e idempotência.

**Framework cobre, sem código local:** execução do grafo de estado e gravação/
restauração de checkpoint são de LangGraph + `SqliteSaver`; o teste de
[reinício e retomada](../tests/test_graph.py#L167) fecha/reabre o saver e retoma
o mesmo thread. Versões fixadas em [requirements.txt](../requirements.txt).

### Quanto custou o que o framework não deu

Contagem de linhas de código (sem docstring nem linha em branco) em
`src/graph.py`, conferida em 2026-10-17:

| Frente | Onde | Linhas | Observação |
|---|---|---|---|
| Motivo de término | `RecommendationResult` [L71-L82](../src/graph.py#L71-L82), `_result` [L226-L234](../src/graph.py#L226-L234), `_event` [L237-L238](../src/graph.py#L237-L238), `resultado_publico` [L618-L624](../src/graph.py#L618-L624) | 30 | `END` não diz por que acabou; `status` + `trajectory` dizem |
| Detector de laço | nenhum | 0 | não há laço no grafo; `recursion_limit=12` só limita o dano |
| Tetos | constantes [L50-L52](../src/graph.py#L50-L52), prazo total em `retrieve` [L369-L373](../src/graph.py#L369-L373), prazo HITL em `approval` [L448-L450](../src/graph.py#L448-L450), `timeout`/`max_retries`/`max_tokens` na chamada, `recursion_limit` em 3 invocações | 17 | dos quatro tetos da Aula 05, o framework cobre só o de passos |
| Erro recuperável × fatal | `except` da interpretação [L291-L302](../src/graph.py#L291-L302) | 10 | erro do modelo vira `status=error` registrado (2 linhas de comentário não contadas); erro de banco não é capturado e sobe |
| Expiração da pausa | `expirar_pendencia` [L589-L602](../src/graph.py#L589-L602), `varrer_pendencias` [L605-L615](../src/graph.py#L605-L615), `src/expirar_pendencias.py` | 39 | o `interrupt` não tem prazo; o checkpoint espera para sempre |

Total: cerca de 96 linhas para o que o LangGraph não oferece, contra zero
linhas para checkpoint, retomada e execução do grafo.

## A decisão que virou parâmetro (§6.6)

**`recursion_limit`.** Na Parte 1, o teto de passos era uma decisão explícita
do laço: `ORCAMENTO = {"max_passos": 8, ...}` em
[src/agent.py](../src/agent.py#L41), comparado a cada volta e com motivo de
parada próprio (`orcamento_passos_estourado`). No
LangGraph essa decisão vira `recursion_limit`, com padrão **25** em
`langgraph/_internal/_config.py:31` (versão 0.6.10). O valor padrão também pode
ser trocado pela variável de ambiente `LANGGRAPH_DEFAULT_RECURSION_LIMIT`, ou
seja, por quem configura o servidor, sem diff nenhum no repositório. O grafo
visita no máximo 5 nós; com 25, um defeito que criasse um ciclo rodaria cinco
vezes mais passos antes de parar. O projeto declara `MAX_NODES = 12` e o passa
em todas as invocações ([L558](../src/graph.py#L558),
[L585](../src/graph.py#L585), [L602](../src/graph.py#L602)), e a versão está
fixada em `requirements.txt`.

**Um segundo caso, já anunciado pela biblioteca.** Toda execução imprime
`LangChainPendingDeprecationWarning: The default value of allowed_objects will
change in a future version`. É o desserializador do checkpoint
(`langgraph/checkpoint/serde/jsonplus.py:36`, `Reviver()` sem argumento), que
hoje aceita a lista `core` de classes. Quando o padrão mudar, checkpoints
gravados com uma versão podem deixar de ser lidos pela seguinte, e uma
aprovação pendente deixa de ser retomável depois de um `pip install -U`. Em
`langgraph-checkpoint==2.1.2` o parâmetro não é exposto pelo `SqliteSaver`, por
isso a defesa é a versão fixada e a regra de não atualizar a biblioteca com
pendências abertas no checkpoint.

## Parâmetros com valor local explícito

`recursion_limit=12`, `temperature=0.2`, `max_tokens=300`, `timeout=20 s`,
`MAX_EVIDENCES=12` (implementado como `limite=12`) e `APPROVAL_TIMEOUT_SECONDS=86400`.
Os defaults de biblioteca podem mudar numa atualização; os valores são
passados explicitamente e a versão do LangGraph/checkpointer é fixada.
