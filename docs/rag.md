# RAG e memória consultável

## Decisão direta

O sistema usa **SQLite para registros/filtros e busca textual lexical para trechos**;
não usa índice vetorial nem embeddings. Não há respostas para relação via grafo
nem agregação em tempo de execução. “RAG” aqui é a recuperação de avaliação
curta para sustentar uma recomendação, não “chat com PDFs”.

Por quê: o corpus tem 18 avaliações curtas, cada uma já é unidade natural de
sentido e precisa ser citada literalmente. Uma busca textual é simples,
explicável e preserva o trecho. Embedding numa base de nove títulos não tem
escala para justificar custo e dependência, e não resolve curadoria/versão.
Disponibilidade, classificação e histórico dependem de igualdade e interseção,
portanto continuam em SQL.

| Forma usada | Implementação | Perguntas do case respondidas |
|---|---|---|
| Consulta estruturada | SQLite: `titulos`, `historico`, filtros por assinatura, classificação e usuário | identidade de título, plataforma listada, elegibilidade, histórico e não repetição |
| Busca textual | `src/rag.py`, tokens normalizados sem acentos; até 12 trechos com ranking determinístico e fonte | termos literais como “mal-estar”, “leve” e citação verificável |

Busca vetorial não implementada (sem modelo de embedding e sem dimensões). Grafo
de conhecimento não implementado: no fixture atual uma consulta relacional seria
um `JOIN`/interseção simples; não existe rede de relações cuja manutenção pague
um banco de grafo. Agregação temática pode ser pré-calculada quando houver
corpus suficiente, mas não orienta hoje uma decisão individual.

## Corpus e curadoria

| Documento | Origem | Mantenedor | Atualização | Tratamento |
|---|---|---|---|---|
| Catálogo e reviews | `dados/streaming_catalog.json`, fixtures autorais | grupo | manual em mudança de versão | dados simulados, não disponibilidade real |
| Corpus textual | `dados/rag_corpus.jsonl`, derivado/copiado das reviews e com ID estável | grupo | reconstrução/revisão a cada alteração do fixture | um review completo por documento; origem/estado anexados |
| Histórico | `dados/historico_seed.jsonl` + transações do app | camada SQLite | por recomendação aprovada | consulta estruturada; nunca indexado como documento público |

Não consultamos TMDB, IMDb, JustWatch ou APIs de streaming. `region` é recebido,
mas não filtra nenhum catálogo real. Dados de avaliação, plataforma e rating são
sintéticos. Para corpus real seria necessário obter fonte autorizada, registrar
licença, região e data de verificação.

### Revogação deliberada

`dark-review-obsolete` afirma que Dark é “leve e cotidiana”, mas está marcado
`status=revoked`, com `replaced_by=dark-review-2`. `buscar_evidencias` filtra o
status **antes** do ranking; um teste pede essa evidência e confirma que não
retorna. A regra de curadoria, não a similaridade, impede que o texto obsoleto
seja usado. Se a revogação não chegasse a `status`, o buscador poderia recuperá-lo.

## Dez perguntas de avaliação e tipo de recuperação

A lista executável fica em `dados/rag_eval.json`; cada item registra a fonte que
responde ou `null` para pergunta sem evidência no corpus.

| ID | Pergunta resumida | Forma adequada | Fonte/resultado esperado |
|---|---|---|---|
| q01 | Em quais plataformas está Dark? | consulta estruturada | `streaming_catalog.json:Dark.platforms` |
| q02 | `u-005` pode receber Dark de novo? *(exceção: histórico bloqueia)* | consulta estruturada | histórico seed; não |
| q03 | Onde aparece “inquietação” de Dark? | busca textual | `dark-review-1` |
| q04 | Qual review de Severance menciona mal-estar? | busca textual | `severance-review-1` |
| q05 | Quais reviews descrevem leveza/cotidiano? | busca textual | `office-review-1`, `office-review-2` |
| q06 | Que título combina com estranhamento/desconforto? | vetorial seria adequada para paráfrase; baseline pode ser lexical | `oa-review-2`, `dark-review-2` |
| q07 | Que títulos compartilham tags com Severance? | grafo se relações crescerem; aqui `JOIN` basta | tags `mood` do fixture |
| q08 | Quais climas são mais recorrentes? | agregação pré-calculada | reviews ativas; não inferir com 18 frases |
| q09 | Pessoa pede leve mas cita Severance: qual vence? *(exceção de interação)* | nenhuma recuperação; regra de precedência | pedido explícito vence referência |
| q10 | Qual título trata de viagens submarinas? *(fora do corpus)* | recuperação apropriada seguida de recusa | sem fonte; suficiência falsa |

A classificação não foi escrita a partir do índice: q01/q02 são perguntas de
registro e exceções reais do workflow, e q09 é política de diálogo. Apenas q06
poderia justificar uma comparação vetorial num corpus maior.

## Corte, limite e chamadas

Não há corte por caracteres nem `k` vetorial. Cada review completo é um chunk;
seu ID, título e fonte permanecem unidos ao texto. A busca lexical retorna no
máximo **12 trechos** (`limite=12`), porque o conjunto ativo atual tem 18 e cada
review é curto. O valor é um teto de implementação, não uma conclusão de
benchmark de relevância. Se corpus crescer, reavaliar cobertura e ruído.

A busca está dentro do nó `retrieve`, antes da proposta. É uma etapa fixa quando
triage encontra clima válido; zero vezes para pedido incompleto, ambíguo, fora
de escopo, assunto fora do corpus ou referência ausente sem clima explícito. O
relatório guarda `retrieval_calls`. O modelo não decide chamar RAG livremente:
essa etapa fixa protege a evidência da proposta.

Nas nove demonstrações de `logs/part2_runs.json` (2026-10-17, commit
`6c3ebf4`, com o modelo no `triage`), houve **5 chamadas** (casos 01, 02, 03, 04
e 06) e **1 chamada inútil**: no caso 01 o modelo leu o clima errado
(`ambiente_pesado` em vez de `mal_estar`), e a busca por esse clima não achou
título elegível. A busca vazia do caso 04 não conta como inútil: ela confirmou
que não havia candidato e impediu a ação. Os outros quatro casos tiveram zero
chamadas. Esse é um juízo operacional nos fixtures, não uma medida estatística
de benefício nem generalização para tráfego real.

## Limitações e resultado

Busca lexical não entende sinônimos nem paráfrases fora do pequeno conjunto de
tags/termos. A decisão de projeto é aceitável para esta prova de conceito por
simplicidade e rastreabilidade. Na próxima entrega, comparar busca lexical e
vetorial com `rag_eval.json`, medir recall@k e precisão das citações, mantendo
as regras de assinatura/classificação/histórico fora do índice semântico.
