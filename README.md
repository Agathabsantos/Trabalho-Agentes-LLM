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

> Curti Severance pelo mal-estar constante. Indica algo parecido.

Identidade, assinaturas, região e classificação são metadados do aplicativo
chamador; não são parte de um formulário digitado. A saída é validada pelo
modelo Pydantic `RecommendationResult`. Exemplo integral copiado da execução
`01_caminho_feliz` em `logs/part2_runs.json`:

```json
{
  "status": "recommendation",
  "title": "Dark",
  "reason": "A avaliacao cita: ‘Sentimento de que algo esta errado o tempo todo.’",
  "platform": "Netflix",
  "confidence": "medium",
  "missing_info": "nenhuma",
  "next_step": "aguardar a reacao do usuario",
  "sufficient": true,
  "sources": [
    {
      "id": "dark-review-2",
      "title": "Dark",
      "text": "Sentimento de que algo esta errado o tempo todo.",
      "source": "dados/streaming_catalog.json:Dark.reviews[1]",
      "score": 1
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
do prazo, vira rejeição sem escrita. `expirar_pendencia` permite ao chamador
agendar o fechamento após 24h, mas o protótipo não inclui daemon ou UI. O
aprovador dos logs é simulado.

## Verificação e reprodução

```bash
python -m unittest discover -s tests -v
python src/demo_part2.py           # nove execuções reproduzíveis; regenera o log
python conferir_grafo.py           # nós/arestas do objeto compilado pelo sistema
python src/verificador.py          # verificador legado; reconstrói dados/catalogo.db
```

O verificador da Parte 1 reconstrói o banco seed e apaga o histórico local do
grafo. Rode-o apenas em uma cópia descartável, nunca enquanto houver sessões ou
aprovações pendentes.

Em 2026-10-16, a suíte rodou **18 testes** e o script gravou nove casos com
regras locais.
Os logs de avaliação não usam API key. O hash `4fe49e86f9415c93edf64f2dbda27921ccab3443`
é o commit-base existente no início da execução; o arquivo registra
`working_tree_dirty: true`, pois as mudanças da Parte 2 ainda não estavam
commitadas. Depois de criar o commit de entrega, rode `python src/demo_part2.py`
novamente para que o SHA reflita a árvore consolidada.

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
