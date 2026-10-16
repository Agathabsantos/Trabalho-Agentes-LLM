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
| `status` | `recommendation`, `no_match`, `clarification`, `out_of_scope`, `rejected` | resultado tipado |
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

As três execuções abaixo vêm de `logs/part2_runs.json`, executadas em
**2026-10-16**, com `source_commit=4fe49e86f9415c93edf64f2dbda27921ccab3443` e
`working_tree_dirty=true`. Esse SHA identifica o commit pai da árvore que foi
executada; não é apresentado como commit final do código desta entrega. Todas
usaram `engine=regras_locais`, `model_calls=0`. Após commit da turma, regenere os
logs para atualizar a proveniência limpa.

### 1. Caminho feliz

Entrada exata: `Curti Severance pelo mal-estar constante. Indica algo parecido.`
Conta sintética: `demo-p2-01`, Netflix, 16+. Execução às
`2026-10-16T23:47:26.613392+00:00`; log [caso 01](../logs/part2_runs.json#L1-L114).

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

O resultado cita o trecho ativo de Dark e registra uma recuperação; a ação só é
persistida após aprovação, registrada na mesma trajetória.

### 2. Recusa por assunto fora do corpus

Entrada exata: `Recomenda um filme de viagem submarina.` Conta sintética:
`demo-p2-05`, Netflix, 16+. Execução às `2026-10-16T23:47:26.674022+00:00`;
log [caso 05](../logs/part2_runs.json#L417-L473).

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

Não há chamada de recuperação porque o assunto está fora das classes locais; a
saída declara a insuficiência e dá próximo passo útil.

### 3. Entrada incompleta

Entrada exata: `Me indica algo parecido.` Conta sintética `demo-p2-07`, Netflix,
16+. Execução às `2026-10-16T23:47:26.693291+00:00`; log
[caso 07](../logs/part2_runs.json#L598-L654).

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

O pedido não é tratado como informação suficiente: o agente pergunta antes de
fazer recuperação ou sugerir um título.

## Casos adicionais de §1.4

- **Ambígua:** `Me recomenda algo leve ou intenso? Ainda nao sei.` →
  `clarification`, exige que a pessoa escolha prioridade; log
  [caso 08](../logs/part2_runs.json#L657-L713).
- **Fora de escopo:** `Qual e a previsao do tempo?` → `out_of_scope`, explica que
  recomenda títulos; log [caso 09](../logs/part2_runs.json#L716-L772).
- **Referência inexistente e contorno seguro:** `Amei O Enigma de Kessler, quero
  misterio e estranheza. Me recomenda algo.` A consulta registra
  `registro_inexistente`, mas o clima explícito permite buscar The OA com fonte
  antes de sugerir; não inventa título substituto. Log
  [caso 03](../logs/part2_runs.json#L232-L343).

## Pausa e idempotência (§8)

Na entrada `Quero algo leve e cotidiano, para rir. Recomenda um titulo.`, a
execução [caso 06](../logs/part2_runs.json#L478-L595) para antes de escrever. A
pessoa aprova editando o motivo e opta por salvar preferência semântica. O log
contém duas respostas de escrita com a mesma chave: primeira
`gravado=true, ja_existia=false`, repetição `gravado=false, ja_existia=true`,
ambas ID 7. Resultado final: The Office/Netflix com `sources` apontando para
`office-review-1`.

## Limites de proveniência

O runner executou o grafo real em banco/checkpoint temporários; o aprovador foi
simulado no script de demonstração. A data e o commit são do log. Essas saídas
não são exemplo de chamada real de LLM nem evidência de catálogo de streaming
atual.
