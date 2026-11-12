# Observabilidade do agente de recomendação

O plano do exercício 15 (`exercicios/aula15-plano-de-observabilidade.md`) foi
feito sobre o agente de trocas do enunciado da aula. Este é o plano **do nosso
case**, seguido da instrumentação que o cumpre e dos números medidos.

## 1. As perguntas

| Interessado | Pergunta | Decisão que a resposta muda |
|---|---|---|
| O negócio | Que fração dos pedidos termina com uma recomendação aprovada pelo responsável, e que fração termina em `no_match`? | Se `no_match` for alto, ampliar o corpus curado antes de ampliar o público; se a aprovação for baixa, rever a escolha do candidato. |
| A operação | Quantas conversas terminam em `erro` ou `orcamento_esgotado`, em qual versão, e em qual ferramenta ou chamada ao modelo? | Voltar à versão anterior do prompt ou do modelo, ou trocar de provedor quando o erro é do `chat`. |
| Quem paga | Quanto custa uma conversa em tokens e em dólares, no p95, e quanto custariam 1.000 conversas por dia? | Ficar no `ministral-8b-2512` ou trocar; sair da camada grátis quando o volume passar do limite dela. |
| Quem responde pelo sistema | Alguma escrita aconteceu sem aprovação humana, algum título passou da classificação do perfil, e algum controle (C1, C3, C4) bloqueou algo? | Suspender a gravação automática e investigar a execução; revogar trecho do corpus que caiu na quarentena. |

## 2. O trace de uma execução

Convenções semânticas GenAI do OpenTelemetry (`src/telemetria.py`). Uma conversa
com aprovação tem duas chamadas ao grafo, ligadas por
`gen_ai.conversation.id = thread_id`:

```text
invoke_agent recomendador            app.operacao=invoke   termino=aguardando_humano
├── execute_tool consultar_titulo    (só se a mensagem cita um título que não está no catálogo)
├── chat ministral-8b-2512           gen_ai.usage.input_tokens / output_tokens, finish_reasons
├── execute_tool consultar_historico
├── execute_tool ler_memoria
├── execute_tool buscar_catalogo     argumentos: clima, plataformas, classificação, excluídos
└── execute_tool buscar_evidencias   resultado: ids devolvidos e ids em quarentena (C3)

invoke_agent recomendador            app.operacao=resume   termino=respondeu
│   evento aprovacao_humana: aprovador, decisão, título, se editou, motivo (limpo por C4), quando
└── execute_tool registrar_recomendacao   resultado: gravado, id, chave de idempotência
```

Atributos próprios da raiz:

| Atributo | Por que existe |
|---|---|
| `app.termination_reason` | separa a execução que terminou bem da que parou no meio; é a base do SLO |
| `app.versao_sistema` (e `service.version` no recurso) | sem ele nenhum número se compara entre versões |
| `app.operacao` | `invoke`, `resume`, `resume_duplicado` ou `expire`: diz qual metade da conversa é |
| `app.decision.status`, `app.decision.title`, `app.decision.sources`, `app.retrieval.ids` | o que foi decidido e com base em que trechos |
| `app.prompt.versao`, `app.prompt.sha256`, `gen_ai.request.model` | sob qual prompt e qual modelo |
| `app.input.message`, `app.input.subscriptions`, `app.input.max_rating`, `app.user_id` | a entrada |
| `app.controles` | qual controle bloqueou o quê nesta execução |

**Motivos de término** (`src/telemetria.py`, `MOTIVOS`): `respondeu`,
`aguardando_humano`, `rejeitado_humano`, `expirado`, `orcamento_esgotado`, `erro`.

**Destino:** um arquivo JSONL por dia em `logs/traces/` (fora do git); a suíte
grava em `evals/resultados/<rodada>/traces.jsonl` (commitado). Para ver:

```bash
python src/ver_trace.py                         # as 5 últimas conversas
python src/ver_trace.py --conversa <thread_id>  # uma conversa inteira
python src/ver_trace.py --arquivo evals/resultados/<rodada>/traces.jsonl --todos
```

## 3. Os modos de falha

| Componente | Falha | Tipo | Sinal que a torna visível |
|---|---|---|---|
| `buscar_evidencias` (RAG lexical) | nenhuma palavra do pedido coincide com as reviews do título certo, e o título some; ou coincide só por "e"/"o" e o trecho citado não sustenta o pedido | **silenciosa** | taxa de `no_match` por clima; veredito `nao_sustenta` do juiz; caso `rec-29` da suíte |
| `chat` (interpretação) | o modelo lê "mal-estar" como `ambiente_pesado` e devolve um JSON válido com o clima errado | **silenciosa** | taxa de acerto da classe `recomendacao` na suíte por versão; `app.mood` no trace comparado com o pedido |
| `retrieve` (teto de 20 s) | a chamada ao modelo demora, o teto estoura e a resposta sai como `no_match` comum | **silenciosa** | `app.termination_reason = orcamento_esgotado`; é o que o SLO mede |
| C3 (quarentena) | uma regex larga demais derruba reviews legítimas, e títulos passam a dar `no_match` | **silenciosa** | contagem de ids em `quarentena` no span `buscar_evidencias`, por versão |
| `chat` (provedor) | 429 da camada grátis, timeout, JSON inválido | ruidosa | `app.termination_reason = erro`, span `chat` com `error.type` |
| C1 (endpoint) | `LLM_BASE_URL` fora da allowlist | ruidosa | `app.controles` com `C1_allowlist_endpoint`; status `error` |

## 4. O objetivo: SLI e SLO

**SLI de qualidade:** fração das conversas concluídas que não terminaram em
`erro` nem em `orcamento_esgotado`.

- **Unidade:** conversa (`gen_ai.conversation.id`); o motivo é o da **última**
  raiz da conversa.
- **Válidos:** conversas cuja última raiz tem `app.termination_reason` diferente
  de `aguardando_humano`.
- **Bons:** válidos com `respondeu`, `rejeitado_humano` ou `expirado` (a recusa
  humana é decisão de quem aprova, não falha do agente).
- **De onde sai:** só do atributo `app.termination_reason` dos spans raiz
  (`evals/metricas.py`).

**SLO:** ≥ 95% numa janela de 7 dias. Orçamento de erro: 5% das conversas.

Este SLO pega a degradação silenciosa do teto de tempo: uma conversa que estoura
os 20 s sai como `no_match`, sem erro, e não mexe na taxa de erro; só o motivo
de término a separa. Ele **não** pega as duas silenciosas de interpretação e de
RAG, que terminam em `respondeu` com resposta pior: essas ficam com a suíte
(classe `recomendacao`) e com o juiz.

## 5. As métricas medidas

⚠ PREENCHER com a saída de
`python -m evals.metricas evals/resultados/1.0.0-modelo-* evals/resultados/1.1.0-modelo-*`
(58 conversas, 29 por versão; cada conversa com aprovação são duas chamadas ao
grafo). Os preços estão em `evals/metricas.py`: US$ 0,15 por milhão de tokens de
entrada e de saída para o `ministral-8b-2512` (página do modelo no OpenRouter,
hospedado pela Mistral, consultada em 2026-11-11). Na camada grátis o custo
cobrado é zero; a conta usa o preço de lista.

| Métrica | 1.0.0 | 1.1.0 |
|---|---|---|
| Conversas | | |
| Latência do agente por conversa, p50 / p95 | | |
| Latência da chamada ao modelo, p50 / p95 | | |
| Custo por conversa, média / p95 | | |
| Custo por 1.000 conversas | | |
| Motivos de término | | |
| Taxa de erro por ferramenta | | |
| SLI / SLO / orçamento consumido | | |

### Respostas às quatro perguntas

⚠ PREENCHER com os números da tabela.

- **Negócio:** __ de __ conversas terminaram com recomendação gravada; __ em `no_match`.
- **Operação:** __ em `erro` e __ em `orcamento_esgotado` na 1.1.0, contra __ na 1.0.0.
- **Quem paga:** US$ __ por conversa (p95 US$ __), US$ __ por 1.000.
- **Quem responde:** nenhuma escrita fora de `resume` aprovado (verificação de
  trajetória da suíte); C3 bloqueou __ trechos e C4 limpou __ motivos.

**Lacuna do plano:** a pergunta do negócio pede a taxa de aprovação humana em
uso real, e as aprovações da suíte são roteirizadas (o `dataset.json` diz quem
aprova o quê). O trace tem o sinal (`aprovacao_humana`), mas o número só vale
com aprovadores reais.
