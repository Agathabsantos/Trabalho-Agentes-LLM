# Arquitetura do agente de recomendação — Parte 2

> Estado implementado em 2026-10-16. Os dados de títulos, disponibilidade e
> avaliações continuam sintéticos. O contrato de entrada é texto livre; os
> metadados da conta chegam do sistema chamador, não de um formulário preenchido
> pela pessoa.

## Diagrama executável

```text
ENTRADA
  mensagem em texto livre + user_id + session_id/thread_id
  + assinaturas, região e classificação fornecidas pelo app
          |
          v
+-----------------------+
| triage                | -- chama modelo 0 ou 1 vez, JSON Pydantic validado
| intenção, clima,      | -- sem API key: parser local explícito
| referência do título  | -- SELECT do catálogo para identificar referência
+-----------+-----------+
            | condicional: código verifica rota e suficiência
            +---- finish: incompleta / ambígua / fora de escopo / referência ausente sem clima explícito
            |
            v
+-----------------------+
| retrieve              | -- SQL: assinatura, classificação, histórico, exclusões
| consulta + RAG textual| -- busca lexical no corpus curado; até 12 trechos
+-----------+-----------+
            | condicional: código lê route
            +---- finish: prazo total excedido -> END
            +---- propose: recuperação concluída
            |
            v
+-----------------------+
| propose               | -- código escolhe candidato elegível com evidência
| proposta rastreável   | -- nenhuma ação persistente antes da pausa
+-----------+-----------+
            | condicional: evidência/candidato existe?
            +---- não: no_match -> END
            |
            v
+-----------------------+
| approval              | -- interrupt: responsável pela conta lê a ação exata
| HITL + edição         | -- aprova / edita / rejeita; validação continua em código
+-----------+-----------+
            | condicional: código valida resposta e prazo
            +---- rejeição / edição inválida / expirada -> END, sem escrita
            |
            v
+-----------------------+
| persist               | -- transação SQLite + SHA-256 do conteúdo como chave
| histórico + episódio  | -- grava uma vez; semântica só com consentimento explícito
+-----------+-----------+
            | incondicional
            v
           END

RECURSOS consultados: dados/catalogo.db (SQLite) + dados/rag_corpus.jsonl
CHECKPOINT: dados/checkpoints.sqlite, endereço = session_id/thread_id
LOG: logs/part2_runs.json; a trajetória registra nós e chamadas de recuperação
```

### Topologia conferida do objeto de produção

Comando: `python conferir_grafo.py`. O script importa `get_graph()` usado pelo
CLI; não cria um grafo demonstrativo.

```text
NOS
approval
persist
propose
retrieve
triage
ARESTAS
START -> triage
approval -> END [condicional]
approval -> persist [condicional]
persist -> END
propose -> END [condicional]
propose -> approval [condicional]
retrieve -> END [condicional]
retrieve -> propose [condicional]
triage -> END [condicional]
triage -> retrieve [condicional]
```

### Quem decide cada aresta condicional

| Origem | Destino | Condição observável | Degrau que decide | Por quê |
|---|---|---|---|---|
| `triage` | `retrieve` | intenção de recomendação e clima válido | modelo interpreta (se configurado); **código** valida campos e roteia | texto livre exige julgamento semântico; destino permanece allowlist de código |
| `triage` | `END` | vazio, ambíguo, fora de escopo, erro de interpretação ou referência ausente sem clima | **código** após interpretação tipada | condição é enum/boolean/`None`; nenhum embedding |
| `retrieve` | `propose` | deadline vigente; consulta concluída | **código** | relógio e rota determinística |
| `retrieve` | `END` | prazo total esgotado | **código** | comparação numérica de tempo |
| `propose` | `approval` | existe candidato com trecho ativo | **código** | teste de lista vazia/evidência, não julgamento adicional |
| `propose` | `END` | nenhum candidato/evidência | **código** | condição verificável |
| `approval` | `persist` | pessoa aprovou e argumentos editados passam os filtros | **código + humano** | humano consente; código valida invariantes |
| `approval` | `END` | rejeição, expiração ou edição inválida | **código** | valores estruturados e prazo |

**Embedding não decide nenhuma aresta.** Não há embeddings no projeto. O modelo
só interpreta entrada aberta em `triage`; as condições e destinos das arestas
são decididos/validados em código.

As condições são determinadas por código; o modelo só ajuda a interpretar o
texto livre no nó `triage`. Saída estruturada reduz erro de formato, mas não
prova que o rótulo semântico escolhido seja correto. Sem chave de API, o grafo
usa regras locais identificadas no log e a cobertura de idioma é menor.

Se uma referência citada não existir, `triage` registra
`lookup_error=registro_inexistente`. Se o mesmo texto contém um clima explícito,
o fluxo continua usando esse clima e sem a referência; se não, devolve
`clarification`. Assim o grafo contorna um registro ausente somente com
informação que a pessoa forneceu, nunca com um título inventado.

## Ferramentas, laço e fronteiras

| Ferramenta/função | Leitura ou escrita | Reversível | Uso no grafo |
|---|---|---|---|
| `CatalogoDB.obter_titulo` | leitura estruturada | n/a | resolve referência; falha vira `registro_inexistente` |
| `CatalogoDB.buscar_por_clima` | leitura estruturada | n/a | aplica assinatura, classificação, histórico e referência excluída |
| `buscar_evidencias` | leitura textual do corpus | n/a | recupera reviews ativos com ID e fonte; revogados são descartados |
| `CatalogoDB.buscar_episodios` | leitura de memória episódica FTS5 | n/a | encontra até 3 eventos anteriores do mesmo usuário; não os trata como gosto |
| `CatalogoDB.registrar_idempotente` | escrita SQLite | idempotente; reversão administrativa por registro | cria histórico, episódio e opt-in semântico na mesma transação |
| `CatalogoDB.atualizar_preferencia` | escrita chave-valor | sobrescrita pela versão mais recente | só após opt-in humano `remember_preference=true` |

Não há laço livre de ferramentas: no máximo uma inferência de interpretação, uma
recuperação e uma pausa. O workflow avança porque cada aresta envia o estado ao
próximo nó. Não há paralelismo, votação ou chamada repetida de avaliador. O
modelo não escolhe ferramenta nem pode relaxar filtros.

## Estado e mensagens

O estado tipado `AgentState` está em `src/graph.py`. `messages` usa o reducer
`add_messages`; `trajectory` e `evidence` usam acumulação de lista. Os campos
escalares são atualizados pelo nó responsável, não compartilhados por ramos
paralelos.

| Campo | Tipo | Quem escreve | Quem lê | Origem |
|---|---|---|---|---|
| `message` | `str` | entrada | triage, retrieve | texto da pessoa |
| `messages` | lista de mensagens + `add_messages` | invocação | checkpoint/depuração | mensagem textual; não é o estado inteiro |
| `user_id`, `session_id`, `subscriptions`, `max_rating`, `region` | escalares | app chamador | triage, retrieve, approval, persist | metadados autenticados devem vir do app real; fixture no CLI |
| `reference_title`, `reference_error`, `mood`, `route` | escalares | triage | retrieve/propose/arestas | texto + interpretação validada; erro do lookup é preservado |
| `candidates`, `candidate_titles` | listas substituídas | retrieve | propose/approval | consulta estruturada |
| `evidence` | lista + reducer aditivo | retrieve | checkpoint/auditoria | histórico de trechos recuperados da thread |
| `current_evidence` | lista substituída | retrieve | propose/persist | só os trechos da mensagem corrente; impede evidência antiga de sustentar nova proposta |
| `decision` | objeto Pydantic serializado | triage, propose, approval, persist | consumidor | contrato de saída |
| `pending_action`, `human_response` | objetos | propose, approval | approval, persist | payload visível e resposta humana |
| `idempotency_key`, `persist_result` | escalares/objeto | approval, persist | persist/consumidor | SHA-256 e retorno `ja_existia` |
| `trajectory` | lista + reducer aditivo | cada nó | logs/diagnóstico | eventos da execução |
| `retrieval_calls`, `model_calls`, `model_tokens` | contadores | retrieve/triage | orçamento/log | chamadas efetivamente feitas |
| `memory_hits`, `semantic_memory` | lista/objeto | retrieve | contexto/auditoria | tabelas SQLite do usuário |
| `started_at`, `prompt_manifest`, `decision_source`, `model_name`, `temperature` | auditoria | triage | limite/log | relógio, hash SHA-256 do prompt e combinação de modelo/parâmetro |

### O que não está no estado

- A conversa em texto fica em `messages`; decisão, limites, identidade, evidência,
  chamada de recuperação e aprovação ficam em campos próprios.
- O catálogo completo, o banco e os bytes do corpus não são copiados para o
  checkpoint. IDs e trechos usados são recalculáveis a partir das fontes.
- O resultado do modelo não inclui raciocínio privado; só o objeto validado.
- Não há agentes filhos; se a Parte 3 os introduzir, devem receber um DTO menor,
  não todo o `AgentState`.

### Reducers: teste observado

O teste `test_reducer_combines_parallel_updates_and_missing_reducer_errors`
executa dois nós paralelos. Com `operator.add`, ambos os valores aparecem. No
controle sem reducer, LangGraph 0.6.10 levanta `InvalidUpdateError` para duas
atualizações no mesmo passo (não sobrescreve silenciosamente). Por isso o
sistema usa reducers nas listas acumuladas, embora seu próprio fluxo não seja
paralelo; os demais campos têm um único escritor por etapa.

## Orçamento, término e falhas

- **Passos:** `recursion_limit=12`, declarado explicitamente na invocação; a
  topologia normal visita até cinco nós.
- **Tempo:** 20 s para timeout da chamada OpenAI; antes da recuperação o grafo
  confere o tempo total decorrido. O limite não cancela uma operação SQLite
  travada; este protótipo local não tem deadline de processo rígido.
- **Tokens:** uma chamada de interpretação, `max_tokens=300` de saída; o total
  de tokens da entrada não é limitado por esse parâmetro e aparece separado
  quando o provedor o informa.
- **Recuperação:** 1 consulta lexical quando há clima buscável e elegibilidade;
  0 se a triagem pergunta/recusa ou a referência ausente não vem acompanhada de
  clima explícito. Um erro de referência com clima informado ainda pode seguir.
- **Candidatos/evidências:** até 12 trechos recuperados.

Términos de negócio: `recommendation`, `no_match`, `clarification`,
`out_of_scope`, `rejected`, proposta pendente (`awaiting_human`). Términos
operacionais: limite de tempo, limite de recursão, falha/JSON inválido do modelo
(sem fallback silencioso) e exceção de banco. Exceção de banco é fatal e sobe
para o chamador; não é convertida em recusa de domínio.

## Nível de autonomia escolhido

O nível é **workflow com router e uma chamada de interpretação**, não agente
com laço livre. Um workflow puramente fixo não bastava para texto livre novo,
conflito entre referência e preferência e distinção entre pedido de
recomendação e fora de escopo; o modelo tipado ajuda no nó `triage`. Não demos
mais autonomia que isso: SQL verifica elegibilidade, RAG fornece evidência, o
código decide o destino das arestas e uma pessoa confirma a escrita. Sem chave,
o parser local executa uma fatia reproduzível, e não é tratado como desempenho
do LLM.

## Padrões da Aula 05

| Padrão | Onde | Por que ele, e não o degrau abaixo | Condição de não uso |
|---|---|---|---|
| sequencial com portão | `retrieve -> propose -> approval -> persist` | valida elegibilidade e interrompe antes de efeito persistente | quando não há escrita ou a proposta não precisa de consentimento |
| router | arestas condicionais de `triage`, `propose`, `approval` | mensagens, evidência e decisão humana levam a destinos diferentes | entrada homogênea e sem ramo de recusa/pausa |
| paralelização / sectioning / voting | não usado | apenas um corpus pequeno e uma decisão; fan-out adicionaria custo | avaliações grandes e verificadores independentes necessários |
| orquestrador-trabalhador | não usado | uma única recomendação não justifica decomposição de agentes | muitas subtarefas independentes |
| avaliador-otimizador | não usado | citação literal e filtros de código; sem reescrita iterativa | quando a qualidade textual precisa de ciclos mensuráveis |
| agente em laço | não usado | custo/autonomia desnecessários; chamada única basta | quando resultados intermediários exigem escolher ferramentas dinamicamente |

## Decisões antes escondidas por padrões

- `max_tokens=300`, `temperature=0.2`, timeout de 20 s, limite de recursão 12,
  limite de evidências 12 e prazo HITL de 24 h estão declarados no projeto.
- O reducer de mensagens é `add_messages`; evidências e trajetória concatenam.
- Se o padrão de LangGraph mudar, a topologia/recursão ou reducer poderiam
  mudar sem diffs locais; por isso os valores estão explícitos e fixados em
  `requirements.txt`.
