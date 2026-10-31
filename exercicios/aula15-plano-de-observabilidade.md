# Plano de observabilidade: agente de trocas

Grupo: Agatha Barbosa Marinho dos Santos, Bruna Kinjo Luiz Pinto, Kayke Ahrens
Biscegli, Matheus da Silva Marini · Data: 2026-10-30

Contexto usado nas contas: cerca de 500 conversas por dia, ou seja, cerca de
14.000 numa janela de 28 dias; no máximo 6 passos por conversa; `registrar_troca`
é a única ferramenta que muda alguma coisa no sistema da loja. A promessa é
resolver 60% das trocas sem atendente, com menos de 1% das trocas aprovadas fora
da política.

---

## 1. Perguntas

| Interessado | Pergunta | Decisão que a resposta muda |
|---|---|---|
| o negócio | Que fração das conversas de troca termina resolvida pelo agente (aprovada ou recusada), sem passar para um atendente? | Manter o agente, ampliar para outras categorias, ou rever a promessa de 60% e o tamanho da equipe de atendimento. |
| a operação | Quantas conversas terminam por orçamento esgotado ou por erro de ferramenta ou de modelo, e em qual versão do agente? | Voltar para a versão anterior do prompt ou do modelo, ou abrir chamado para o sistema de pedidos quando a falha é de ferramenta. |
| quem paga | Quanto custa, em tokens e em reais, cada troca resolvida pelo agente, comparado ao custo de um atendente humano? | Trocar o modelo por um mais barato, cortar passos, ou concluir que o agente não se paga. |
| quem responde pelo sistema | Quantas trocas o agente registrou fora da política (fora do prazo da categoria ou sem cumprir as condições)? | Suspender o registro automático e exigir aprovação de um atendente antes de `registrar_troca`, além de revisar as trocas já registradas. |

---

## 2. O *trace* de uma conversa

**Árvore de *spans* de uma conversa típica** (troca aprovada; o modelo do exemplo
é o `mistral-small-latest`):

```text
invoke_agent  agente-de-trocas
├── chat mistral-small-latest           (o modelo pede consultar_pedido)
├── execute_tool consultar_pedido       (data da compra, produto, categoria, valor)
├── chat mistral-small-latest           (o modelo pede consultar_politica)
├── execute_tool consultar_politica     (prazo e condições da categoria)
├── chat mistral-small-latest           (o modelo pede registrar_troca)
├── execute_tool registrar_troca        (a única escrita no sistema da loja)
└── chat mistral-small-latest           (o modelo responde ao cliente)
```

São 4 chamadas ao modelo e 3 ferramentas, dentro do orçamento de 6 passos. Numa
recusa, o `execute_tool registrar_troca` não aparece; num encaminhamento, a
árvore termina sem ele e com `troca.decisao = encaminhada`.

Cada `chat` carrega `gen_ai.request.model`, `gen_ai.usage.input_tokens`,
`gen_ai.usage.output_tokens` e `gen_ai.response.finish_reasons`; cada
`execute_tool` carrega `gen_ai.tool.name` e `gen_ai.tool.call.id`; a raiz carrega
`gen_ai.agent.name = agente-de-trocas` e `gen_ai.provider.name`. A versão do
agente (prompt e modelo) vai em `service.version`, atributo de recurso do
OpenTelemetry, para que a pergunta da operação possa comparar a versão no ar com a
anterior.

**Atributos próprios na raiz:**

| Atributo | Valores possíveis | Para que serve |
|---|---|---|
| `troca.decisao` | `aprovada`, `recusada`, `encaminhada` | Responde à pergunta do negócio: resolvidas sem atendente são `aprovada` + `recusada`. Nenhuma convenção sabe que existe "encaminhar". |
| `agente.termino` | `respondeu`, `orcamento_esgotado`, `erro_ferramenta`, `erro_modelo` | Separa a conversa que terminou bem da que parou no meio. Um encaminhamento por orçamento esgotado conta como `encaminhada` em `troca.decisao`, mas é falha, não cautela. |
| `troca.conferencia_politica` | `dentro`, `fora`, `nao_registrada` | Gravado pelo **código**, não pelo modelo: no momento do `registrar_troca`, a aplicação compara a data da compra com o prazo devolvido por `consultar_politica`. É o que mede a parte "menos de 1% fora da política" da promessa sem depender do julgamento do próprio agente. |

---

## 3. Modos de falha

| Componente | Falha | Ruidosa ou silenciosa | Sinal que a torna visível |
|---|---|---|---|
| modelo + `registrar_troca` | O modelo conta errado os dias desde a compra, ou registra sem ter consultado a política, e aprova uma troca fora do prazo. | **silenciosa**: o cliente recebe "troca aprovada" e o registro entra no sistema da loja | `troca.conferencia_politica = fora` com `troca.decisao = aprovada`; e, no mesmo *trace*, um `execute_tool registrar_troca` sem nenhum `execute_tool consultar_politica` antes dele |
| `registrar_troca` | O cliente repete a mensagem, ou o modelo repete a chamada, e a mesma troca é registrada duas vezes para o mesmo pedido. | **silenciosa**: a ferramenta devolve sucesso nas duas | Mais de um `execute_tool registrar_troca` com o mesmo número de pedido, no mesmo *trace* ou em *traces* diferentes; contagem por pedido > 1 |
| modelo | Depois de uma troca de versão do prompt ou do modelo, o agente fica cauteloso demais e encaminha casos simples, ou entra em laço chamando `consultar_pedido` de novo até gastar os 6 passos. | **silenciosa**: a conversa termina com uma resposta educada de encaminhamento | Fração de `troca.decisao = encaminhada` subindo; `agente.termino = orcamento_esgotado`; *traces* que usam os 6 passos ou repetem a mesma ferramenta |
| `consultar_pedido` e API do modelo | O sistema de pedidos fica fora do ar ou demora, ou a API do modelo devolve erro 429 ou 5xx. | **ruidosa**: a ferramenta ou a chamada levanta erro | *Span* com status `ERROR` e `error.type`; `agente.termino = erro_ferramenta` ou `erro_modelo`; latência do *span* `execute_tool consultar_pedido` |

---

## 4. Objetivos

| Tipo | Indicador | Objetivo | Janela |
|---|---|---|---|
| operacional | conversas com `agente.termino = respondeu` ÷ total de conversas | ≥ 97% (cerca de 420 das 14.000 conversas podem terminar por erro ou orçamento) | 28 dias, móvel |
| a promessa da loja (resolução) | conversas com `troca.decisao` em `aprovada` ou `recusada` ÷ total de conversas | ≥ 60% | 28 dias, móvel |
| a promessa da loja (conformidade) | conversas com `troca.conferencia_politica = fora` ÷ conversas com `troca.decisao = aprovada` | < 1% | 28 dias, móvel |

As duas linhas da promessa andam juntas de propósito: a forma mais fácil de
subir a resolução é aprovar mais, e é exatamente isso que a conformidade vigia.

---

## 5. Alertas

| Alerta | Condição e limiar | SLO de origem | Quem é avisado | O que faz |
|---|---|---|---|---|
| custo | Conversas que esgotam o orçamento acima de 3% na última hora (com pelo menos 20 conversas na hora). Uma conversa que esgota os 6 passos é a mais cara e não resolve nada; 3% é o mesmo erro tolerado pelo SLO operacional. Acompanha também a média de `gen_ai.usage.input_tokens + output_tokens` por conversa, comparada com a dos últimos 7 dias. | operacional: ≥ 97% das conversas terminam com `respondeu` | o responsável técnico pelo agente | Abre os *traces* com mais *spans* `chat`, compara a versão no ar com a anterior e, se a alta começou com uma troca de versão, volta para a anterior. |
| degradação silenciosa | Trocas aprovadas com `troca.conferencia_politica = fora` acima de 1% das aprovadas nas últimas 24 horas (com pelo menos 30 aprovações na janela). | promessa da loja (conformidade): < 1% fora da política | quem responde pelo sistema (o dono do produto) e, em cópia, a supervisão do atendimento | Desliga o registro automático: `registrar_troca` passa a exigir confirmação de um atendente. Depois revisa as trocas registradas fora da política no período, uma a uma, pelos *traces*. |

---

## Como saber, sem ler o código, se o agente funciona e se funciona bem

**Se funciona:** o SLO operacional responde. A fração de conversas com
`agente.termino = respondeu`, e os *spans* com status `ERROR`, mostram se o
agente termina as conversas, sem abrir uma linha de código.

**Se funciona bem:** só os atributos de domínio respondem, porque uma conversa
pode terminar sem erro e mesmo assim estar errada. `troca.decisao` mostra se a
promessa de 60% está sendo cumprida. `troca.conferencia_politica`, calculado pelo
código e não pelo modelo, mostra se essa resolução está sendo comprada com
aprovações fora da política. Os dois alertas avisam quem pode agir antes que a
janela de 28 dias feche no vermelho.
