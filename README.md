# Agente de recomendação de títulos em streaming

Trabalho da disciplina de agentes com LLM, em três partes sobre o mesmo sistema.

## Integrantes

- Agatha Barbosa Marinho dos Santos
- Bruna Kinjo Luiz Pinto
- Kayke Ahrens Biscegli
- Matheus da Silva Marini

## O que o sistema faz

O sistema recebe **texto livre** sobre o que a pessoa quer sentir ("quero algo
leve e cotidiano, para rir") e recomenda o próximo título sem repetir o que já
foi recomendado, sem sair da assinatura e sem furar a classificação do perfil.
Ele consulta o catálogo e as avaliações curadas, filtra por assinatura,
classificação e histórico, propõe uma opção citando a avaliação que a sustenta e
**para para o responsável pela conta** aprovar, editar ou rejeitar a gravação no
histórico.

O sistema atual é um grafo LangGraph (`src/graph.py`) com uma única chamada de
modelo, no nó que interpreta o texto. Filtros, busca, escolha do candidato e
escrita ficam no código.

## Estado da entrega

| Parte | O que está entregue | Onde |
|---|---|---|
| Parte 1 | agente com laço de ferramentas, verificador e análise de modelos; mantido como baseline | `src/agent.py`, `docs/case.md`, `docs/modelos.md`, `docs/model-card.md` |
| Parte 2 | grafo LangGraph, RAG lexical, memória, pausa humana, idempotência e 9 casos demonstrados com o modelo | `src/graph.py`, `docs/`, `logs/part2_runs.json` |
| Exercício 14 | os dez riscos OWASP para agentes no case, com mitigações implementadas para ASI02, ASI03 e ASI08 | `exercicios/aula14-respostas.md` |
| Exercício 15 | plano de observabilidade do agente de trocas | `exercicios/aula15-plano-de-observabilidade.md` |

O detalhe do que está pronto e do que falta fica em `docs/estado-da-entrega.md`.

## Rodar do zero

Python 3.11 ou mais novo (validado com 3.13 e 3.14.7):

```bash
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env             # Windows: copy .env.example .env
python -m unittest discover -s tests -v
python src/demo_part2.py
```

O `.env` é opcional. Sem chave, o grafo interpreta o texto com regras locais, e
os logs dizem `engine=regras_locais`; essa execução nunca é apresentada como
resultado do modelo. Para usar o modelo, preencha no `.env` `OPENAI_API_KEY`,
`MODEL_NAME` e, se for a Mistral, `LLM_BASE_URL=https://api.mistral.ai/v1`. A
chave nunca é versionada.

Para conversar com o agente pelo terminal:

```bash
python src/graph.py --message "Quero algo leve e cotidiano, para rir. Recomenda um titulo." --user-id u-demo --subscriptions Netflix --max-rating 16+
```

O CLI mostra a proposta e pede `aprovar`, `rejeitar` ou um JSON com edição. O
responsável pode, por exemplo, aprovar corrigindo `reason` e marcando
`remember_preference: true` para guardar o clima como preferência. Nada é gravado
antes da aprovação. O banco SQLite e o checkpoint são criados em `dados/` na
primeira execução; não os apague enquanto houver conversa pendente.

## Como usar e o que volta

**Texto que a pessoa digita:**

> Quero algo leve e cotidiano, para rir. Recomenda um titulo.

Identidade, assinaturas, região e classificação são metadados do aplicativo
chamador, não um formulário digitado. A saída é validada pelo modelo Pydantic
`RecommendationResult`. Exemplo integral copiado da execução
`06_pausa_edicao_idempotencia` em `logs/part2_runs.json` (2026-10-17, commit
`6c3ebf4`, árvore limpa, com o modelo `ministral-8b-2512` no `triage`):

```json
{
  "status": "recommendation",
  "title": "The Office",
  "reason": "Edicao humana: o trecho descreve leveza e humor cotidiano.",
  "platform": "Netflix",
  "confidence": "high",
  "missing_info": "nenhuma",
  "next_step": "aguardar a reacao do usuario",
  "sufficient": true,
  "sources": [
    {
      "id": "office-review-1",
      "title": "The Office",
      "text": "Bem leve e engracada.",
      "source": "dados/streaming_catalog.json:The Office.reviews[0]",
      "score": 2
    }
  ]
}
```

`sources` permite conferir a justificativa. `sufficient=false` significa que não
há base para recomendar e que o título é `null`: recusa é saída normal, não
exceção. Os outros status são `no_match`, `clarification`, `out_of_scope`,
`rejected` e `error` (a chamada ao modelo falhou). Os contratos e os exemplos
completos, com data, commit e referência ao log, ficam em `docs/io.md`.

**Se o grafo parar:** a pessoa vê o título, a plataforma, o trecho que sustenta a
sugestão, a consequência da gravação e o prazo de 24 horas. Responde aprovando,
editando ou rejeitando. Silêncio não aprova: a conversa fica pendente no
checkpoint e, depois do prazo, vira rejeição sem gravar nada. O aprovador dos
logs é simulado; o protótipo não tem interface gráfica.

## Resultados medidos

- **Testes:** 24, todos passando, em 2026-10-23. Eles rodam sem modelo mesmo com
  chave no `.env`.
- **Demo com o modelo:** `ministral-8b-2512`, commit `6c3ebf4`, árvore limpa,
  **8 de 9 casos com o status esperado**. O caso 01 falhou porque o modelo leu
  "mal-estar" como `ambiente_pesado`; está registrado como falha em
  `docs/io.md`, sem ajuste no esperado.
- **Teste A/B da frase do prompt:** 90 chamadas; a frase de segurança fica, mas
  quase não protege contra injeção. A defesa real é o código. Resultado em
  `docs/prompts.md` e `logs/ab_frase_prompt.json`.

## Segurança

A análise completa dos dez riscos está em `exercicios/aula14-respostas.md`. O que
já está no código:

- as ferramentas da Parte 1 usam só o usuário da sessão; um `user_id` vindo do
  modelo é recusado;
- sem classificação do perfil, vale a mais restrita (`L`), nunca `18+`;
- a varredura de expiração segue para as outras conversas quando uma falha;
- remoção a pedido do titular apaga histórico, memória e checkpoint, e depois
  varre de novo procurando o identificador.

O que **não** existe: autenticação de quem usa ou aprova, e verificação de hash
dos pacotes (risco aceito e declarado). O sistema é uma prova de conceito local.

## Comandos

```bash
python -m unittest discover -s tests -v   # 24 testes, sem modelo
python src/demo_part2.py                  # 9 casos do grafo; regenera logs/part2_runs.json
python conferir_grafo.py                  # nós e arestas do grafo que o sistema executa
python src/ab_frase.py --repeticoes 5     # teste A/B da frase do prompt; exige chave
python src/expirar_pendencias.py          # rejeita aprovações pendentes há mais de 24h (cron, de hora em hora)
python src/remover_titular.py <user_id>   # remoção a pedido do titular, com varredura depois
```

Com chave no `.env`, a demo chama o modelo e o log registra `engine=modelo`,
`model_calls=1` e tokens por caso. Se algum caso divergir do esperado, o log é
gravado mesmo assim (`matches_expected=false`) e o script termina com código de
erro listando os casos. Rode a demo depois de commitar, para o log registrar
`working_tree_dirty=false`.

Parte 1 (baseline):

```bash
python src/agent.py                       # 5 casos com o modelo; exige chave
python src/agent.py --sem-modelo          # mesmo laço com regras fixas, sem LLM
python src/verificador.py                 # confere contra o gabarito e as invariantes
python src/verificador.py --autoteste
```

O verificador reconstrói o banco a partir do seed e apaga o histórico local do
grafo. Rode-o só numa cópia descartável, nunca com conversas ou aprovações
pendentes.

## Estrutura

- `src/graph.py`: o grafo, o contrato de saída, a interpretação, a busca, a pausa, a escrita idempotente, a expiração e a remoção.
- `src/catalogo_db.py`: única porta de acesso ao SQLite, com os filtros de autoridade e a memória.
- `src/rag.py`: busca textual no corpus curado, com fonte e filtro de revogação.
- `src/prompts/`: prompts versionados, carregados em tempo de execução.
- `src/demo_part2.py`, `src/ab_frase.py`, `src/expirar_pendencias.py`, `src/remover_titular.py`: demo, teste A/B e rotinas operacionais.
- `src/agent.py`, `src/motores.py`, `src/ferramentas.py`, `src/verificador.py`, `src/benchmark_modelos.py`: agente e verificação da Parte 1.
- `tests/`: testes do grafo e dos limites de autoridade.
- `dados/`: catálogo sintético, corpus curado, dataset de avaliação e históricos.
- `logs/`: execuções registradas (demo da Parte 2, A/B do prompt, benchmark e demos da Parte 1).
- `docs/`: documentação de projeto (lista abaixo).
- `exercicios/`: respostas dos exercícios das aulas.
- `conferir_grafo.py`: conferência do grafo de produção.

A implementação **não** consulta TMDB, Netflix, Prime Video nem outra API de
catálogo. Títulos, avaliações, serviços e classificações são dados simulados
pelo grupo, não disponibilidade real.

## Documentos

- `docs/estado-da-entrega.md`: o que está pronto e o que falta.
- `docs/case.md`: o domínio, as ferramentas e o complemento da Parte 2.
- `docs/arquitetura.md` e `docs/grafo.md`: diagrama, topologia conferida, estado e decisões.
- `docs/io.md`: contrato de entrada e saída e exemplos copiados dos logs.
- `docs/prompts.md`: plano de prompts, mudança da v1 para a v2 e teste A/B.
- `docs/rag.md` e `dados/rag_eval.json`: corpus, dez perguntas e escolha da busca.
- `docs/memoria.md`: checkpoint, memória longa, volume gravado e remoção por titular.
- `docs/humano.md`: pausa, edição, prazo, expiração e idempotência.
- `docs/modelos.md` e `docs/model-card.md`: análise de modelos e model card da Parte 1.
- `docs/fontes.md`: fontes consultadas.
