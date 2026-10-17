# Agente de recomendação de títulos em streaming — Parte 2

## Integrantes

- Agatha Barbosa Marinho dos Santos
- Bruna Kinjo Luiz Pinto
- Kayke Ahrens Biscegli
- Matheus da Silva Marini

O sistema recebe **texto livre** sobre o que a pessoa quer sentir, consulta o
catálogo e as avaliações curadas, filtra por assinatura/classificação/histórico,
propõe uma opção citada por evidência e **para para o responsável pela conta**
aprovar, editar ou rejeitar a escrita no histórico.

## Rodar do zero

Python 3.11+ recomendado (validado com Python 3.13.5):

```bash
python3 -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env            # opcional para o modelo; sem chave, usa parser local
python src/demo_part2.py
python -m unittest discover -s tests -v
```

Para uma chamada interativa, sem chave de modelo:

```bash
python src/graph.py --message "Curti Severance pelo mal-estar constante. Indica algo parecido." --user-id u-demo --subscriptions Netflix --max-rating 16+
```

O CLI mostra a proposta e pede `aprovar`, `rejeitar` ou JSON com edição. O
responsável pode, por exemplo, aprovar corrigindo `reason` e marcando
`remember_preference: true`. Não há escrita antes da aprovação. O banco SQLite
e o checkpoint são criados em `dados/` na primeira execução; ambos são locais e
não devem ser apagados enquanto houver conversa pendente.

O modo de interpretação com LLM é opcional. Para ativá-lo, preencha no `.env`
`OPENAI_API_KEY`, `MODEL_NAME` e, se aplicável, `LLM_BASE_URL`. A chave nunca é
versionada. Sem chave, os logs dizem `regras_locais`; essa execução não é
apresentada como resultado do modelo. O grafo usa zero ou uma chamada de modelo,
uma busca de evidência e exige aprovação humana.

## Como usar e o que volta

**Texto que a pessoa digita:**

> Quero algo leve e cotidiano, para rir. Recomenda um titulo.

Identidade, assinaturas, região e classificação são metadados do aplicativo
chamador; não são parte de um formulário digitado. A saída é validada pelo
modelo Pydantic `RecommendationResult`. Exemplo integral copiado da execução
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

`source`/`sources` permite conferir a justificativa. `sufficient=false` significa
que não há base suficiente e que o título é `null`; recusa é saída normal,
não exceção. Os contratos e exemplos completos, com data, commit e referência
exata a log, ficam em `docs/io.md`.

**Se o grafo parar:** a pessoa vê título, plataforma, trecho-fonte, consequência
da escrita e prazo de 24h. Responde aprovando, editando ou rejeitando. Silêncio
não aprova: a execução fica pendente no checkpoint; se a retomada ocorrer depois
do prazo, vira rejeição sem escrita. `python src/expirar_pendencias.py`, rodado
de hora em hora por cron, rejeita as pendências vencidas; o protótipo não inclui UI. O
aprovador dos logs é simulado.

## Verificação e reprodução

```bash
python -m unittest discover -s tests -v
python src/demo_part2.py           # nove execuções reproduzíveis; regenera o log
python conferir_grafo.py           # nós/arestas do objeto compilado pelo sistema
python src/expirar_pendencias.py   # rejeita aprovações pendentes há mais de 24h
python src/remover_titular.py <user_id>  # remoção a pedido do titular, com varredura
python src/ab_frase.py             # teste da frase do prompt (§2.3); exige chave no .env
python src/verificador.py          # verificador legado; reconstrói dados/catalogo.db
```

Com `OPENAI_API_KEY` e `MODEL_NAME` no `.env`, o mesmo `python src/demo_part2.py`
passa a chamar o modelo no nó `triage`, e o log registra `engine=modelo`,
`model_calls=1` e tokens por caso. Se o status de algum caso divergir do
esperado, o log é gravado mesmo assim (`matches_expected=false`) e o script
termina com código de erro listando os casos.

O verificador da Parte 1 reconstrói o banco seed e apaga o histórico local do
grafo. Rode-o apenas em uma cópia descartável, nunca enquanto houver sessões ou
aprovações pendentes.

Em 2026-10-17, a suíte rodou **20 testes** (eles rodam sem modelo mesmo com
chave no `.env`). A demo rodou com o modelo `ministral-8b-2512` no commit
`6c3ebf4`, com `working_tree_dirty=false`: **8 de 9 casos com o status
esperado**. O caso 01 falhou porque o modelo leu "mal-estar" como
`ambiente_pesado`; está registrado como falha em `docs/io.md`, sem ajuste no
esperado. O teste A/B da frase do prompt está em `logs/ab_frase_prompt.json` e
em `docs/prompts.md`.

## Estrutura principal

- `src/graph.py`: `StateGraph`, contrato Pydantic, interpretação, RAG, pausa e escrita idempotente.
- `src/catalogo_db.py`: SQLite, filtros de autoridade e memória local.
- `src/rag.py`: recuperação textual com fonte e filtro de revogação.
- `src/prompts/`: prompts versionados e carregados durante a execução.
- `dados/`: catálogo sintético, corpus curado, dataset de avaliação e históricos.
- `docs/`: case complementado, arquitetura, memória, RAG, HITL, I/O e prompts.
- `logs/part2_runs.json`: nove trajetórias de execução.
- `conferir_grafo.py`: inspeção do grafo de produção.

A implementação **não** consulta TMDB, Netflix, Prime Video ou outra API de
catálogo. Títulos, opiniões, serviços e classificações nos fixtures são dados
simulados pelo grupo, não disponibilidade atual. O sistema é uma prova de
conceito local, sem autenticação de contas ou garantia operacional LGPD.

## Documentos

- `docs/case.md` — domínio e complemento da Parte 2.
- `docs/arquitetura.md` e `docs/grafo.md` — diagrama, topologia, estado e decisões.
- `docs/rag.md` e `dados/rag_eval.json` — corpus, dez perguntas e escolha de busca.
- `docs/memoria.md` — checkpoint, memória longa e limites de remoção.
- `docs/humano.md` — pausa, edição, prazo e idempotência.
- `docs/prompts.md` — plano e limites do teste do prompt.
- `docs/io.md` — schema e exemplos copiados dos logs.
- `docs/modelos.md`, `docs/fontes.md` — análise da Parte 1 e fontes técnicas.
