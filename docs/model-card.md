# Model card: agente de recomendação de títulos em streaming

Versão do sistema descrita: **1.1.0** (`src/versao.py`). O card da Parte 1, que
descreve o laço com tool calling (`src/agent.py`), foi preservado em
`docs/model-card-parte1.md`.

Regra de leitura: nos campos Autoridade, Avaliação, Riscos aceitos e Registro e
retenção, cada afirmação aponta para a evidência no repositório, ou leva a marca
**LACUNA [Lnn]**, reunida na última seção com a correção proposta.

## 1. Identificação

Agente de recomendação de títulos em streaming, protótipo local em Python.
Grafo LangGraph com cinco nós (`triage`, `retrieve`, `propose`, `approval`,
`persist`) em `src/graph.py`. Grupo: Agatha Barbosa Marinho dos Santos, Bruna
Kinjo Luiz Pinto, Kayke Ahrens Biscegli e Matheus da Silva Marini. Repositório
`Agathabsantos/Trabalho-Agentes-LLM`.

## 2. Finalidade

Recebe um texto livre sobre o que a pessoa quer sentir e propõe **um** título
do catálogo que esteja na assinatura, dentro da classificação do perfil e fora
do que já foi recomendado, citando o trecho de avaliação que sustenta a escolha.
A gravação no histórico só acontece depois que o responsável pela conta aprova.

**Fora de escopo:** reproduzir conteúdo, comprar, alterar assinatura, consultar
disponibilidade real (o catálogo é sintético), atender usuários reais.

## 3. Autoridade

| Limite | Onde é aplicado | Evidência |
|---|---|---|
| **Escopo:** propor um título e gravar a proposta aprovada no histórico local | ausência de ferramenta | o grafo não tem ferramenta de compra, reprodução, assinatura ou envio de mensagem; as únicas escritas são `registrar_idempotente` e a remoção pelo titular (`src/catalogo_db.py`) |
| **Ações proibidas:** o modelo escolher título, plataforma ou filtro | código (arquitetura) | o modelo só devolve `Interpretation` (intenção, clima, ambiguidade), validada como `Literal` (`src/graph.py:331`); a escolha é SQL e ordenação em `src/graph.py:419-470` |
| **Assinatura** | código | busca em `src/catalogo_db.py` (`buscar_por_clima`) e revalidação da edição humana em `src/graph.py:539-545`; teste `TestC2AutoridadeDoPerfil.test_aprovador_nao_troca_para_titulo_fora_da_assinatura` |
| **Classificação; sem valor vale `L`** | código | `src/catalogo_db.py:27-33`; teste `TestC2AutoridadeDoPerfil.test_sem_classificacao_nao_propoe_titulo_14_mais` |
| **Não repetir o histórico** | código | exclusão em `src/graph.py` (nó `retrieve`, `excluded`); caso `rec-08-historico` da suíte |
| **Credencial** | credencial | uma chave do provedor no `.env`, que só serve para inferência; o SQLite é arquivo local com a permissão do usuário do SO. **LACUNA [L01]**: a chave da camada grátis da Mistral não tem escopo nem limite configurável por nós |
| **Endpoint do modelo só em `api.mistral.ai` ou `api.openai.com`, por https** | código | C1, `src/seguranca.py:18-35`, aplicado em `src/graph.py:286-300`; teste `TestC1AllowlistEndpoint` |
| **Limite por execução:** 1 chamada ao modelo, 300 tokens de saída, 20 s, 12 passos do grafo | código | `src/graph.py:55-56`, `max_tokens=300` e `timeout` na chamada, `recursion_limit=MAX_NODES` em `invocar`; verificação de trajetória `no_maximo_uma_chamada_ao_modelo` da suíte |
| **Limite de gasto** | plataforma | camada grátis (plano Experiment) da Mistral, que limita requisições por segundo e por mês. **LACUNA [L02]**: não há teto de gasto em dinheiro configurado, porque não há cartão; ao sair da camada grátis, configurar o limite no console |
| **Limiar de aprovação humana:** toda gravação, sem exceção | código | `persist` só é alcançável a partir de `approval` (arestas em `src/graph.py`), que começa com `interrupt` (`src/graph.py:509`); verificação de trajetória `escrita_so_depois_de_aprovacao` |
| **Silêncio não aprova:** pendência vence em 24 h | código | `src/graph.py` (`expirar_pendencia`, checagem do prazo no nó `approval`); caso `rec-24-expirada`; `test_expired_approval_rejects_on_resume` |
| **Comportamento quando um controle falha** | código | C1 e C2 são fail-closed (`error` ou `no_match`, sem chamada e sem escrita); C3 e C4 são fail-open com registro (`docs/seguranca.md`, seção 3); exceção do provedor vira `status=error` sem escrita (`src/graph.py`, `except` do `triage`) |
| **Quem pode suspender o agente** | plataforma | quem tem acesso à máquina: apagar a chave do `.env` desliga o modelo (o grafo cai nas regras locais, rotuladas `regras_locais` no trace). **LACUNA [L03]**: não há chave de suspensão que pare também as escritas, nem pessoa nomeada |
| **Quem aprova** é o responsável pela conta | prompt e processo | **LACUNA [L04]**: não há autenticação; o aprovador é quem conhece o `thread_id`. O trace grava `app.aprovador` quando o app manda e `nao_identificado` quando não (`src/telemetria.py`, `fechar_raiz`) |

## 4. Ferramentas e integrações

| Ferramenta (nome no trace) | Leitura ou escrita | Contra o quê |
|---|---|---|
| `consultar_titulo` | leitura | SQLite `dados/catalogo.db` via `CatalogoDB` |
| `consultar_historico` | leitura | SQLite, tabela `historico` |
| `ler_memoria` | leitura | SQLite, `episodios` (FTS5) e `memoria_semantica` |
| `buscar_catalogo` | leitura | SQLite, filtros de clima, assinatura, classificação e exclusões |
| `buscar_evidencias` | leitura | `dados/rag_corpus.jsonl` (busca lexical, com C3) |
| `registrar_recomendacao` | escrita reversível, idempotente | SQLite, `historico`, `episodios`, `memoria_semantica` |
| Modelo | inferência | API da Mistral, compatível com a da OpenAI, pela biblioteca `openai` |

Não há MCP, multiagente nem mídia. Nenhuma ferramenta é chamada pelo modelo: o
grafo chama todas.

## 5. Modelo e provedor

`ministral-8b-2512` (Mistral), camada grátis, `https://api.mistral.ai/v1`,
temperatura 0,2, `response_format=json_object`, até 300 tokens de saída. Prompt
`src/prompts/interpret_request.txt` **v2** (few-shot), com o SHA-256 gravado em
todo trace (`app.prompt.sha256`). A escolha e as alternativas estão em
`docs/modelos.md`.

## 6. Dados

Catálogo, corpus, usuários e histórico são **sintéticos**
(`dados/streaming_catalog.json`, `dados/rag_corpus.jsonl`,
`dados/historico_seed.jsonl`). Em uso real, o texto do pedido, o histórico e a
classificação do perfil seriam dado pessoal. Ao modelo vai só o texto do pedido.
O mapa completo (prompt, índice, memória, checkpoint, trace e provedor, com
finalidade, base legal e prazo) está em `docs/seguranca.md`, seção 5.

## 7. Avaliação

| Afirmação | Evidência |
|---|---|
| Golden dataset v1.0.0 com 29 casos em 5 classes, 8 de recusa, 9 de desenvolvimento e 20 sintéticos | `evals/dataset.json`; `docs/evals.md` |
| Na versão 1.1.0 com o modelo, __% dos casos passam (por classe: __) | ⚠ PREENCHER: `evals/resultados/1.1.0-modelo-<data>/resumo.json` |
| A 1.1.0 melhorou a classe `seguranca` sem piorar as outras, em relação à 1.0.0 | ⚠ PREENCHER: saída de `evals.comparar` em `docs/evals.md`, seção 4 |
| O juiz da propriedade "evidência sustenta o pedido" foi validado | ⚠ PREENCHER: `evals/juiz/validacao_resultado.json`. Até lá, **LACUNA [L05]**: o juiz não está adotado |
| 33 testes passam, 9 deles dos controles desta entrega | `python -m unittest discover -s tests`; `tests/test_controles.py` |

## 8. Limites conhecidos

- **RAG lexical:** a evidência é escolhida por palavras em comum, inclusive "e".
  O título certo some quando nenhuma palavra coincide (`rec-29`), e o trecho
  citado pode não ter relação com o pedido (itens da validação do juiz).
- **Interpretação:** o modelo leu "mal-estar" como `ambiente_pesado` na Parte 2
  (caso 01) e obedece a instruções no próprio texto (ASI01, `rec-26`).
- **Catálogo de 9 títulos e 19 trechos:** sem disponibilidade real.
- **Um turno:** o agente não conversa para refinar; pergunta e encerra.

## 9. Riscos aceitos

| Risco | Evidência |
|---|---|
| ASI01, injeção direta pelo próprio usuário | `docs/seguranca.md`, seção 4; medido pelo caso `rec-26-injecao-direta` (⚠ PREENCHER o resultado com o modelo) e no A/B da Parte 2 (`logs/ab_frase_prompt.json`, `i02`, 5 de 5) |
| ASI04, pacotes sem hash | `docs/seguranca.md`, seção 4; versões fixadas em `requirements.txt` |
| ASI03(c), aprovador sem autenticação | `docs/seguranca.md`, seção 4; LACUNA [L04] |

## 10. Supervisão humana

O responsável pela conta aprova, edita ou rejeita toda gravação, vendo ação,
título, plataforma, trecho e consequência (`docs/humano.md`). A edição é
revalidada pelo código (C2). Silêncio vira rejeição em 24 h.

## 11. Registro e retenção

**O registro é o trace** (`src/telemetria.py`). Cada chamada ao grafo grava um
span raiz com entrada, ids dos trechos recuperados, versões do sistema, do
prompt e do modelo, ferramentas com argumentos e resultado, saída, motivo de
término e, na retomada, o evento `aprovacao_humana` (quem, quando, o quê, se
editou).

**Retenção e acesso:** os traces de uso ficam em `logs/traces/` (fora do git);
os da suíte, em `evals/resultados/*/traces.jsonl` (commitados, com usuários
sintéticos). Prazo declarado: **90 dias** para traces de uso; quem lê: os quatro
integrantes do grupo, com acesso à máquina. Como o trace guarda o texto do
pedido e o `user_id`, ele herda a classificação de dado pessoal. **LACUNA
[L06]**: não há rotina que apague traces com mais de 90 dias.

### Decisão reconstruída só a partir do trace

⚠ PREENCHER com um trace da rodada com o modelo. Comando:

```bash
python src/ver_trace.py --arquivo evals/resultados/1.1.0-modelo-<data>/traces.jsonl --conversa rec-28-corpus-envenenado-<data>
```

Roteiro da reconstrução (o caso `rec-28` é o melhor exemplo, porque mostra um
controle agindo):

1. **Entrada:** `app.input.message`, `app.input.subscriptions`, `app.input.max_rating` da raiz `invoke`.
2. **Versões:** `app.versao_sistema`, `app.prompt.versao`, `app.prompt.sha256`, `gen_ai.request.model`.
3. **O que o modelo entendeu:** `app.mood`; tokens no span `chat`.
4. **Com base em quê:** `buscar_catalogo` (argumentos e títulos devolvidos),
   `buscar_evidencias` (ids devolvidos e o id que caiu na quarentena),
   `app.retrieval.ids` e `app.decision.sources`.
5. **O que foi proposto e aprovado:** `app.pending_action` na raiz `invoke`;
   evento `aprovacao_humana` na raiz `resume`.
6. **O que mudou no mundo:** resultado de `registrar_recomendacao` (id e chave
   de idempotência); motivo de término `respondeu`.

## 12. Histórico de mudanças

Em `docs/mudancas.md`.

## Lacunas

| Id | Lacuna | Correção proposta |
|---|---|---|
| L01 | Chave sem escopo nem limite configurável | Conta paga com chave por ambiente e limite de gasto no console |
| L02 | Sem teto de gasto em dinheiro | Configurar no console ao sair da camada grátis |
| L03 | Sem chave de suspensão que pare escritas | Variável `AGENTE_SUSPENSO` lida no nó `persist`, fail-closed, com teste |
| L04 | Aprovador sem autenticação | O app hospedeiro autentica e manda `approver`; o grafo recusa resposta sem ele |
| L05 | Juiz não adotado até a validação | Rotular os 20 itens e rodar `evals.validar_juiz` |
| L06 | Sem rotina de expiração de traces | Rodar com o cron da expiração: apagar `logs/traces/*.jsonl` com mais de 90 dias |
| L07 | Checkpoint guarda a resposta bruta do aprovador, antes de C4, sem prazo | Limpar a resposta antes do `Command(resume)` no app e expirar threads concluídas |
| L08 | Política de retenção do provedor não verificada | Ler e registrar os termos da API da Mistral antes de dado real |
