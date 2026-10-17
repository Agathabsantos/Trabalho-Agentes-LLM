# Contrato de entrada e saída

## Entrada

A entrada obrigatória do sistema é `message: str`, texto livre em português.
Metadados do app, não digitados pela pessoa: `user_id`, `session_id` (também o
`thread_id`), assinaturas, região e classificação máxima. O caso de demonstração
usa dados sintéticos; em produto real o app deve derivar identidade/assinatura de
uma sessão autenticada.

## Saída Pydantic

`RecommendationResult` valida todas as terminações:

| Campo | Tipo/valores | Uso |
|---|---|---|
| `status` | `recommendation`, `no_match`, `clarification`, `out_of_scope`, `rejected`, `error` | resultado tipado; `error` = a chamada ao modelo ou a validação da resposta falhou |
| `title` | string ou `null` | só título elegível com evidência |
| `reason` | string | justificativa sem inventar fatos |
| `platform` | string ou `null` | plataforma da interseção da assinatura |
| `confidence` | `low`, `medium`, `high` | ordinal heurístico, **não** probabilidade calibrada |
| `missing_info` | string | informação faltante, se houver |
| `next_step` | string | ação esperada |
| `sufficient` | boolean | se há base suficiente para recomendar |
| `sources` | lista de `Evidence` | ID, título, trecho literal, origem e score lexical |

Uma recomendação só sai com `sufficient=true` e `sources` não vazia. Recusa,
pergunta de esclarecimento e fora de escopo têm `title=null`, `sufficient=false`
e `sources=[]`. A confirmação pendente é envelope de transporte (`awaiting_human`)
que inclui payload da ação; ainda não é uma decisão final para consumo.

## Exemplos copiados dos logs

As execuções abaixo vêm de `logs/part2_runs.json`, gravado em **2026-10-17**
com `source_commit=6c3ebf4a2a663ebe3ae3b1e6acc5bc66625d3a7e` e
`working_tree_dirty=false`: o código que rodou é exatamente o desse commit.
Todas usaram o modelo no nó `triage` (`engine=modelo`,
`model_name=ministral-8b-2512`, `temperature=0.2`, `model_calls=1`).
Resultado da demo: **8 de 9 casos com o status esperado**. O caso que falhou
está descrito logo abaixo dos exemplos, sem ajuste no esperado.

### 1. Caminho feliz

Entrada exata: `Quero algo leve e cotidiano, para rir. Recomenda um titulo.`
Conta sintética: `demo-p2-06`, Netflix, 16+. Execução às
`2026-10-17T00:47:14.588756+00:00`; log [caso 06](../logs/part2_runs.json#L514-L651).

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

O que ler ali: o modelo leu "leve" e devolveu a tag `leve`; o código achou um
único título elegível com trecho ativo, e a recomendação cita esse trecho em
`sources`. O `reason` é o texto editado pela pessoa na aprovação (§8.2).

### 2. Recusa por assunto fora do corpus

Entrada exata: `Recomenda um filme de viagem submarina.` Conta sintética:
`demo-p2-05`, Netflix, 16+. Execução às `2026-10-17T00:47:13.343988+00:00`;
log [caso 05](../logs/part2_runs.json#L439-L513).

```json
{
  "status": "no_match",
  "title": null,
  "reason": "O corpus curado nao contem evidencia suficiente sobre esse assunto; nao vou inventar uma recomendacao.",
  "platform": null,
  "confidence": "low",
  "missing_info": "uma evidencia de catalogo sobre o assunto solicitado",
  "next_step": "refinar para um clima coberto ou atualizar o corpus",
  "sufficient": false,
  "sources": []
}
```

O que ler ali: o modelo devolveu `mood=null` (é assunto, não clima), e o código
recusou sem fazer busca (`retrieval_calls=0`), com `sufficient=false` e um
próximo passo útil.

### 3. Entrada incompleta

Entrada exata: `Me indica algo parecido.` Conta sintética `demo-p2-07`, Netflix,
16+. Execução às `2026-10-17T00:47:15.798087+00:00`; log
[caso 07](../logs/part2_runs.json#L652-L726).

```json
{
  "status": "clarification",
  "title": null,
  "reason": "Ainda nao sei qual clima voce quer; diga o que gostou ou o que quer sentir.",
  "platform": null,
  "confidence": "low",
  "missing_info": "o motivo do gosto ou clima desejado",
  "next_step": "perguntar ao usuario",
  "sufficient": false,
  "sources": []
}
```

O que ler ali: o pedido não é tratado como suficiente; o agente pergunta antes
de buscar ou sugerir um título.

### O caso que falhou com o modelo

Entrada: `Curti Severance pelo mal-estar constante. Indica algo parecido.`
Esperado: recomendação. Obtido: `no_match`; log
[caso 01](../logs/part2_runs.json#L2-L90). O modelo escolheu a tag
`ambiente_pesado` em vez de `mal_estar`; com essa tag não havia título elegível,
e o sistema recusou em vez de inventar. A falha é de interpretação do modelo:
o mesmo erro aparece em 5 de 5 chamadas no teste A/B (`docs/prompts.md`). Com
as regras locais, este caso recomenda Dark. O resultado fica registrado como
está; o esperado não foi alterado.

## Casos adicionais de §1.4

- **Ambígua:** `Me recomenda algo leve ou intenso? Ainda nao sei.` vira
  `clarification` e pede que a pessoa escolha a prioridade; log
  [caso 08](../logs/part2_runs.json#L727-L801).
- **Fora de escopo:** `Qual e a previsao do tempo?` vira `out_of_scope` e
  explica que o agente recomenda títulos; log
  [caso 09](../logs/part2_runs.json#L802-L876).
- **Referência inexistente:** `Amei O Enigma de Kessler, quero misterio e
  estranheza. Me recomenda algo.` A consulta registra `registro_inexistente`, e
  o código segue com o clima que a própria mensagem traz (o modelo leu
  `surreal`). Resultado: The OA, com fonte; nenhum título substituto foi
  inventado. Log [caso 03](../logs/part2_runs.json#L222-L351).

## Pausa e idempotência (§8)

Na entrada `Quero algo leve e cotidiano, para rir. Recomenda um titulo.`, a
execução [caso 06](../logs/part2_runs.json#L514-L651) para antes de escrever. A
pessoa aprova editando o motivo e opta por salvar a preferência semântica. O log
contém duas respostas de escrita com a mesma chave: a primeira
`gravado=true, ja_existia=false` e a repetição `gravado=false, ja_existia=true`,
ambas com ID 6.

## Limites de proveniência

O runner executou o grafo real em banco e checkpoint temporários; o aprovador foi
simulado no script de demonstração. A data e o commit são do log. Os títulos,
avaliações e plataformas são fixtures sintéticas, não catálogo de streaming
atual.
