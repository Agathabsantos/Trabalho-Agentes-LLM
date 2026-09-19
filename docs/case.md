# Case — recomendação do próximo título a partir do motivo do gosto

> Versão 2 — revisada em 19/09/2026. A v1 está no histórico do git.
> O que mudou: as ferramentas passaram a refletir a implementação real, o
> verificador virou código executável, o critério de sucesso ganhou a métrica
> assimétrica, e a linha de base foi rebaixada de "medida" para "estimativa a
> medir", porque a medição ainda não foi feita.

## 1. O problema

**Problema em uma frase:** um agente que identifica o motivo exato do gosto do usuário em um título e recomenda a próxima série ou filme disponível na conta, sem repetir itens e sem sugerir algo fora do perfil ou fora da assinatura.

**Quem sofre com ele hoje:** o assinante de streaming que abre o app à noite com 40 minutos livres e gasta os primeiros 15 rolando catálogo em vez de assistir.

**Contexto de uso:** o sistema roda num chat dentro de um app próprio de recomendação — não é um recurso dentro da Netflix ou do Prime. A pessoa abre o app já com a intenção de descobrir o que assistir. Antes do agente, ela abre cada plataforma, filtra por gênero ou nota e recebe listas que não explicam por que aquilo foi escolhido. Depois do agente, ela aceita ou recusa a sugestão, e essa reação volta para o histórico.

**O que acontece hoje sem ele:** a pessoa rola o catálogo, usa filtros de gênero e compara manualmente entre plataformas. O processo se repete a cada sessão, e a frustração maior é descobrir que a sugestão está num serviço que ela não assina.

**Regras do domínio:**
1. o título recomendado precisa estar em plataforma assinada pelo usuário;
2. não pode repetir título já recomendado ou recusado por aquele usuário;
3. a recomendação precisa respeitar a classificação indicativa do perfil da sessão;
4. gasto extra ou assinatura fora do pacote exige confirmação do responsável pela conta.

**O que dá errado hoje:**
- a recomendação responde ao gênero, não ao motivo do gosto;
- a mesma sugestão volta em conversas diferentes;
- a sugestão aparece em plataforma que a pessoa não assina;
- a sessão em grupo ou o perfil infantil recebe recomendação incompatível;
- a pessoa diz "gostei de Severance", mas o que a agradou foi o clima de mal-estar, não o rótulo de suspense corporativo.

O último é o caso difícil que define o sistema: **a mesma frase de entrada esconde intenções diferentes**, e o rótulo de gênero não distingue as duas.

## 2. Usuários e como o agente conversa com eles

### 2.1 Perfis

| Perfil | O que ele quer | O que ele sabe | O que ele **pode** fazer |
|---|---|---|---|
| **Assinante (usuário principal)** | decidir rápido o que assistir | sabe o que gostou, mas nem sempre sabe explicar por quê | pede recomendação, aceita, recusa, responde refinamento |
| Responsável pela conta | evitar gasto extra e manter o perfil dentro das regras | conhece assinatura, perfis e restrições | **aprova ou bloqueia** recomendação paga ou incompatível |
| Pessoa assistindo junto | que a sugestão funcione para o grupo | sabe o que o grupo gosta, mas não informa de cara | aceita ou recusa a sugestão compartilhada |

**Usuário principal: o assinante.** Quando os interesses conflitam — o negócio quer retenção no app, o assinante quer sair da tela rápido — o sistema é desenhado para o assinante.

**Quem pode aprovar ação irreversível:** o responsável pela conta. Como o sistema da Parte 1 **não tem nenhuma ação irreversível** (a única escrita é o registro no histórico, revertível por `Ferramentas.reverter_escritas`), esse perfil ainda não é acionado. Ele existe porque a Parte 2, ao adicionar sugestão de conteúdo pago, cria a primeira ação que precisa de confirmação.

### 2.2 Como é a interação

- **Canal:** chat dentro do app de recomendação. O canal é chat porque a entrada é texto livre que o usuário não consegue estruturar sozinho — se ele soubesse preencher um formulário com "clima: mal-estar constante", não precisaria do sistema. **O que a Parte 1 entrega desse canal:** só o laço por trás dele. Não há interface de chat ainda; o agente roda por linha de comando, os pedidos vêm de `dados/cases.json` e a saída é o JSON abaixo. O chat é o canal **previsto**, e a interface é escopo da Parte 2 junto com o refinamento em várias trocas.
- **Quem começa:** o usuário. O agente é reativo, não proativo, e não manda notificação.
- **Quantas trocas:** na Parte 1, **uma**. O contexto da conta (assinatura, classificação, histórico) é injetado pelo código, então o agente não precisa perguntar o que o sistema já sabe. O refinamento em várias trocas é escopo da Parte 2 — ver §10 (LangChain).
- **O que devolve:** um objeto JSON com `status`, `title`, `reason`, `platform`, `confidence`, `missing_info` e `next_step`. O contrato está em `prompts/system.txt`.
- **Como termina:** com `recommendation` e um título, ou com `no_match` e o motivo pelo qual o catálogo assinado não atende ao pedido. Nunca com uma sugestão inventada.

### 2.3 Diálogo de exemplo

> **Usuário:** "Curti muito Severance. Me indica algo parecido."
>
> **Agente:** "O que te prendeu mais em Severance: o mistério corporativo ou o clima de mal-estar constante?"
>
> **Usuário:** "O clima estranho."
>
> **Agente:** "Então **Dark**, na sua Netflix. O catálogo marca esse título com mal-estar e mistério — as mesmas tags de Severance —, e as avaliações citam a sensação de que há algo errado o tempo todo. Quer outra opção?"
>
> **Usuário:** "Só Dark por enquanto."

E o diálogo que termina sem sugestão:

> **Usuário:** "Estou com vontade de uma série intensa e estranha, tipo Severance, mas sem pagar nada extra."
>
> **Agente:** "Não consigo. Na sua assinatura só entra o Prime Video, e o único título com esse clima lá é 16+, acima do que este perfil aceita. Ou você libera outro perfil, ou eu procuro um clima diferente."

Esses dois diálogos são os casos `caso_simples` e `nao_dispara_acao` em `dados/cases.json`.

### 2.4 A complexidade real de interação

- **O que o usuário não informa de primeira:** o motivo do gosto. Ele diz o título; o motivo é o que o sistema precisa inferir do texto livre e cruzar com as tags do catálogo.
- **Quando o usuário contradiz o sistema:** em `divergencia_usuario_vs_sistema`, a pessoa cita Severance (intensa) mas pede "algo leve". A política é explícita no prompt: **o pedido do usuário vence a referência que ele citou**. Recomendar algo pesado porque Severance é pesada seria responder ao rótulo, que é exatamente o erro que o sistema existe para corrigir.
- **Como o sistema decide que sabe o suficiente:** quando `buscar_candidatos` devolve ao menos um título que passa nos três filtros (assinatura, classificação, histórico). Se devolve zero, o sistema não sabe o suficiente e para.
- **Quando para e chama um humano:** quando a única saída exigiria gasto extra ou quebra de restrição de perfil. Aí quem decide é o **responsável pela conta**, não o assinante.

## 3. O workflow do agente

```
1. ENTRADA        pedido em texto livre + contexto da conta      [decide: CÓDIGO]
                  (assinatura, classificação, user_id)

2. REFERÊNCIA     consulta o título citado no catálogo           [decide: MODELO]
                  -> se não existe: ERRO devolvido como dado         (chama a ferramenta)
                  -> o agente decide se contorna ou encerra

3. INTENÇÃO       decide QUAL clima buscar: o da referência      [decide: MODELO]
                  ou o que o usuário pediu, quando divergem

4. CANDIDATOS     filtra por assinatura, classificação e         [decide: CÓDIGO]
                  histórico; devolve só o que sobrou

5. ESCOLHA        escolhe um candidato e justifica com a         [decide: MODELO]
                  evidência do catálogo

6. ESCRITA        grava no histórico                             [ESCRITA — reversível]
                  -> revalida as 3 invariantes antes de gravar   [decide: CÓDIGO]
                  -> se recusa, devolve o motivo ao modelo

7. RETORNO        entrega o JSON ao usuário, ou no_match         [decide: CÓDIGO]
                  com o motivo da recusa

8. PARADA         registra POR QUE parou: resposta_final,        [decide: CÓDIGO]
                  orçamento estourado ou erro do modelo
```

**Quem decide:** passos 1, 4, 6 (validação), 7 e 8 são código; passos 2, 3 e 5 são do modelo. O passo 6 é o único misto — o modelo pede a escrita, o código decide se ela acontece.

**Escritas:** só o passo 6. É **reversível** (`Ferramentas.reverter_escritas` apaga o registro pelo id). Por ser reversível, não exige confirmação humana. A primeira ação irreversível aparece na Parte 2, com sugestão de conteúdo pago, e aí o confirmante é o responsável pela conta.

## 4. O sistema

**O que o sistema faz:** recebe um pedido em texto livre, consulta o catálogo num banco SQLite através de uma camada de acesso, decide qual clima o usuário realmente quer (que nem sempre é o do título que ele citou), escolhe um candidato entre os que passaram nos filtros de assinatura, classificação e histórico, e devolve a recomendação com a evidência que a sustenta — ou `no_match`, quando nada atende.

**Nível de autonomia: agente simples** (laço com ferramentas, o modelo escolhe a próxima chamada).

**Por que não o nível de baixo.** Um **roteador** classificaria o pedido em rotas fixas e chamaria a busca certa. Ele resolveria o `caso_simples`, e quebra em dois pontos:

1. **A divergência.** Em `divergencia_usuario_vs_sistema`, decidir entre o clima da referência e o clima pedido depende de ler as duas coisas em texto livre e julgar qual vence. Não é uma classificação em N rotas conhecidas — o espaço de "climas" é aberto, e ele é construído em tempo de execução a partir da frase.
2. **O erro de ferramenta.** Em `registro_inexistente`, a ferramenta falha e o agente precisa decidir o que fazer com a falha: contornar buscando por outro caminho, ou encerrar sem inventar. Um roteador tem rota fixa por entrada, não por resultado intermediário.

É nesses dois pontos que o agente se paga. Em todo o resto — filtro, validação, escrita — a decisão é do código, e deve continuar sendo.

### As ferramentas

| Ferramenta | O que faz | Leitura ou escrita? | Reversível? | Contra o que ela conversa |
|---|---|---|---|---|
| `consultar_titulo` | detalhes de um título pelo nome | leitura | n/a | SQLite, tabela `titulos`, via `catalogo_db.py` |
| `buscar_candidatos` | títulos compatíveis com um clima, já filtrados por assinatura, classificação e histórico | leitura | n/a | SQLite, tabela `titulos`, via `catalogo_db.py` |
| `consultar_historico` | o que já foi oferecido a este usuário | leitura | n/a | SQLite, tabela `historico` |
| `registrar_recomendacao` | **grava** a decisão no histórico | **escrita** | **sim** — `reverter_escritas()` apaga pelo id | SQLite, tabela `historico` |

Nenhuma delas levanta exceção para o laço: toda falha volta como `{"erro", "detalhe", "como_corrigir"}`. O campo `como_corrigir` é o que permite ao modelo se recuperar sozinho em vez de repetir a mesma chamada.

**A integração com software tradicional (item 4.2):** o catálogo e o histórico vivem num banco **SQLite** (`dados/catalogo.db`), acessado exclusivamente por `src/catalogo_db.py`. Nenhuma parte do agente lê arquivo de dados diretamente. O banco é reconstruído a cada execução a partir dos dados simulados versionados, para que o projeto rode do zero sem passo manual. **Na Parte 2, essa camada é reescrita como servidor MCP** — foi escolhida pensando nisso.

## 5. A justificativa de negócio

### 5.1 Por que um agente, e não software comum

A tarefa exige decisão em tempo de execução em dois pontos que um formulário não cobre: **(a)** quando o clima pedido contradiz o título citado como referência, é preciso ler as duas coisas em texto livre e julgar qual vence — e o conjunto de climas possíveis não é uma lista fechada que caiba num `select`; **(b)** quando uma ferramenta falha, é preciso decidir entre contornar e encerrar, e essa decisão depende do resultado intermediário, não da entrada.

O nível abaixo — roteador — não dava conta porque roteador escolhe entre rotas conhecidas na entrada, e aqui a escolha acontece depois da primeira consulta, sobre um espaço de opções que só existe em tempo de execução.

Tudo o mais é código, e continua sendo: o filtro por assinatura, a classificação, o histórico e a validação da escrita são regras determinísticas. **Cinco dos oito passos do workflow são decididos por código.**

### 5.2 O ganho esperado

**Eixo escolhido: tempo por tarefa** (minutos até a decisão de o que assistir). Foi escolhido porque é o único que o grupo consegue **cronometrar** sem acesso a dados de produção. Não prometemos redução de erro de recomendação porque não temos como medir isso com 5 casos.

**Linha de base medida em 19/09/2026 — 10 decisões cronometradas.** Protocolo:
cronômetro do "abri o app" ao "cliquei em play", sem alterar o comportamento;
sessões que terminaram sem escolha **contam** e estão marcadas. Mediram os 4
integrantes e 5 pessoas de fora do grupo (amigos), o que evita que a amostra
seja só de quem construiu o sistema.

| # | Quem | Plataformas abertas | Minutos | Decidiu? |
|---|---|---|---|---|
| 1 | Matheus (grupo) | Netflix, Prime | 13 | sim |
| 2 | Jessica | Netflix, Disney+ | 6 | sim |
| 3 | Lucas | Prime, HBO Max, Netflix | 21 | **não** |
| 4 | Antonio | Netflix, Prime, Disney+ | 23 | **não** |
| 5 | Carla | Netflix | 4 | sim |
| 6 | Bruna (grupo) | Prime, Netflix, YouTube | 9 | sim |
| 7 | Kayke (grupo) | Netflix, HBO Max | 8 | sim |
| 8 | Agatha (grupo) | Disney+, Netflix, Prime | 17 | **não** |
| 9 | Matheus (grupo) | Prime | 5 | sim |
| 10 | Ana | Netflix, HBO Max | 11 | sim |

| | Valor | Origem |
|---|---|---|
| Linha de base | **11,7 min por decisão** (mediana 10; mín 4, máx 23) | **medida**, 10 cronometragens acima |
| Alvo | 2 min por decisão, **medido até o mesmo ponto da base: o play** | ~1 min no app de recomendação (uma troca + ler a justificativa) + ~1 min para abrir a plataforma indicada, achar o título e dar play. **Estimativa**, não medida |
| Conta | de 11,7 para 2 min = **−83%** por decisão | sobre a média medida |
| Volume | 200 decisões/dia → 2.340 min/dia hoje, 400 com o agente: **−1.940 min/dia (~32 h)** | volume **hipotético**, não observado |

**A estimativa anterior era 14 min e a medição deu 11,7.** O ganho caiu de −86%
para −83%, e é o número menor que fica. Se tivéssemos mantido os 14 sem medir,
estaríamos prometendo 3 pontos percentuais que não existem.

**O que a medição mostrou que a estimativa não mostrava:**

- **3 das 10 sessões (30%) terminaram sem escolher nada**, e são as mais
  longas — média de 20,3 min contra 8,0 min das que decidiram. Ou seja, o
  tempo perdido se concentra nas sessões que **já não produzem nada**. É
  exatamente o caso que o agente ataca, e é um segundo eixo de ganho
  (cobertura) que não prometemos porque 3 ocorrências não sustentam
  promessa — fica anotado para a Parte 3 medir.
- **O tempo cresce com o número de plataformas abertas:** 1 plataforma →
  4,5 min; 2 → 9,5 min; 3 → 17,5 min. Sustenta a premissa do tema — o problema
  não é falta de conteúdo, é excesso de catálogo — com dado, não com opinião.

**Ressalva.** O alvo de 2 min inclui a ida até a plataforma porque o agente roda num app separado — não dá play, aponta onde está o título. Se a troca de app custar mais que o estimado, o ganho cai; isso só se mede com o sistema em uso, e é o que a Parte 3 vai conferir. Dez medições, uma por sessão, sem repetição controlada. É uma
amostra pequena e a média tem variação alta (desvio de 4 a 23 min). Serve
para substituir o chute por um número observado, não para afirmar precisão.
O alvo de 2 min e o volume de 200/dia continuam sendo **estimativas**, e a
conta inteira é declarada como tal — o enunciado pede que seja.

**Ganho para o negócio:** mais sessões que terminam em reprodução em vez de abandono; menos custo de navegação por sessão.

**Ganho para o usuário:** decide em uma troca em vez de quinze minutos de rolagem; nunca recebe sugestão que não consegue assistir; não vê a mesma sugestão duas vezes.

**A tensão entre os dois:** o negócio tem incentivo para manter a pessoa no app o máximo possível — tempo de tela é a métrica que a indústria acompanha. O usuário quer exatamente o contrário: sair da tela rápido. Um sistema otimizado para tempo de sessão pioraria deliberadamente a recomendação. **Escolhemos o assinante**, e por isso a métrica do sistema é tempo *até a decisão*, que cai quando o sistema acerta — o oposto de tempo de sessão. É o erro do caso Klarna visto em aula: a métrica acompanhada melhorava enquanto a que importava piorava.

### 5.3 O outro lado da conta

- **Custo de rodar:** **US$ 0,000850 por execução** (medido: 5.668 tokens × US$ 0,15/1M no `ministral-8b-2512`), ou **US$ 30,61 por semestre** a 200 execuções/dia. Conta completa em `docs/modelos.md` §3.
- **Custo de construir:** 4 pessoas, uma entrega de prova de conceito. O custo real não foi o código — foi construir os casos difíceis e o verificador.
- **O que se perde:** o sistema erra quando o clima pedido é vago ("quero algo bom"). Nesse caso ele devolve `no_match` em vez de chutar, e **quem paga é o usuário**, que sai sem resposta e volta a rolar o catálogo. Escolhemos esse custo conscientemente: uma recomendação errada que o usuário não consegue assistir custa mais confiança do que um "não sei".

## 6. O verificador

O verificador **existe e é executável**: `src/verificador.py`. Ele confere duas coisas, porque o custo do erro é assimétrico.

**(A) Acerto contra gabarito rotulado à mão.** Os 5 casos de `dados/cases.json` têm `expected_title` e `expected_status` preenchidos por nós, e o verificador compara com a decisão registrada em `logs/demo_runs.json`.

**(B) Invariantes de domínio, conferidas contra o banco.** Independentemente de acertar o título esperado, a decisão é reprovada se:
1. o título não estiver em plataforma assinada;
2. o título estiver acima da classificação do perfil;
3. o título já tiver sido oferecido àquele usuário;
4. o título não existir no catálogo (alucinação).

**O verificador é testado contra si mesmo.** `python src/verificador.py --autoteste` injeta quatro decisões sabidamente erradas — uma por invariante — e falha se alguma passar batido. Um verificador que aprova tudo é pior que nenhum, porque dá falsa segurança.

> O gabarito **não é visível ao agente.** `expected_title` e `expected_status`
> são lidos só pelo verificador. Na v1 deste projeto o agente lia esses campos
> e acertava por isso; foi corrigido.

## 7. O critério de sucesso

**≥ 4 acertos em 5 casos rotulados E zero violações de invariante.**

As duas métricas existem porque o custo do erro é assimétrico: recomendar um título fora da assinatura é muito pior que recomendar um título compatível mas não ideal. No primeiro caso o usuário clica e não consegue assistir; no segundo ele só recusa e pede outro. **Uma violação de invariante reprova a execução inteira, mesmo com 5/5 acertos** — e é assim que o `verificador.py` está implementado (código de saída 1).


### Resultado medido, em 18/09/2026

| Execução | Modelo | Acertos | Violações | Veredicto |
|---|---|---|---|---|
| `logs/demo_runs.json` | `ministral-8b-2512` | **5/5** | **0** | APROVADO |

Critério atendido. Nenhum caso falhou nesta execução, e por isso não há aqui
nenhuma linha de "caso X errou porque Y" — se houvesse, ela estaria escrita,
e não o gabarito ajustado.

### Defeito encontrado e corrigido no laço de tool calling

Registrado aqui porque **não aparece no placar acima** e ainda assim mudou a
análise de modelos.

**O defeito.** `src/motores.py` anexava ao histórico a mensagem inteira do
assistente, com todas as tool calls que ela trazia, mas processava apenas a
primeira e devolvia uma única resposta. Se o modelo emitisse duas chamadas em
paralelo, a requisição seguinte ficava com N chamadas e 1 resposta, e o
provedor recusava com `400 invalid_request_message_order`.

**Como apareceu.** O `ministral-8b-2512` nunca emitiu chamadas paralelas nos 5
casos — por isso o 5/5 sempre saiu. O `ministral-3b-2512` emite, e quebrou em 2
dos 5 casos na primeira rodada do benchmark (18/09). Sem o benchmark, o defeito
teria ido para a entrega escondido atrás de um placar perfeito.

**A correção (19/09).** `MotorModelo` ganhou uma fila (`_fila_de_chamadas`):
quando o modelo pede N ferramentas, a primeira é executada na hora e as demais
saem nas voltas seguintes do laço, cada uma com sua resposta, **sem nova chamada
à API**. O laço em `agent.py` não mudou: continua uma ferramenta por passo, um
registro por passo na trajetória, orçamento contado do mesmo jeito.

**Verificação.** 12 execuções do 3B nos dois casos que quebravam: **0 erros
HTTP** (antes: 1 em 6). Benchmark rodado de novo nos 3 modelos: 0 erros HTTP.
`demo_runs.json` regenerado com o código corrigido: 5/5, 0 violações.

**O que a correção revelou.** Com o crash fora do caminho, o 3B mostrou uma
limitação real que estava escondida: no caso de divergência, ele faz as
chamadas certas, recebe o candidato certo e **se recusa a recomendá-lo** em
~50% das vezes. Detalhe em `docs/modelos.md` §4. É o motivo pelo qual a escolha
do modelo ficou no 8B e não desceu para o 3B, mais barato.

## 8. Dados

Os dados são **simulados**, o que o enunciado autoriza, e foram construídos para preservar a dificuldade do problema. Ficam em `dados/`:

| Arquivo | O que é |
|---|---|
| `streaming_catalog.json` | 9 títulos com clima, plataforma, classificação, sinopse e avaliações |
| `historico_seed.jsonl` | histórico inicial de 3 usuários, que alimenta a regra de não-repetição |
| `cases.json` | os 5 casos de teste, com gabarito |
| `catalogo.db` | o SQLite derivado dos dois primeiros (não versionado) |

Os casos difíceis, nomeados explicitamente:

| Caso | O que ele força | Esperado |
|---|---|---|
| `caso_simples` | o caminho feliz tem que funcionar | Dark |
| `divergencia_usuario_vs_sistema` | usuário cita Severance (intensa) mas pede "algo leve" — **a referência contradiz o pedido** | The Office |
| `registro_inexistente` | o título de referência não existe; a ferramenta devolve erro e **o agente tem que contornar sem inventar** | `no_match` |
| `nao_dispara_acao` | a única plataforma assinada não tem nada dentro da classificação do perfil — **não pode recomendar nada** | `no_match` |
| `nao_repete_recomendacao` | o melhor candidato já foi oferecido antes — **tem que oferecer o próximo** | The OA |

**Por que os dados não são fáceis demais:** o catálogo tem só 9 títulos, mas as restrições cruzadas (plataforma × classificação × histórico) fazem com que 2 dos 5 casos não tenham resposta possível. Um catálogo grande e sem restrição tornaria todos os casos triviais; o que cria a dificuldade aqui é a interseção, não o tamanho.

## 9. Dado sensível

Este tema **não toca dado sensível** — não há dado pessoal identificável, financeiro, de saúde ou sigiloso. Os `user_id` são sintéticos (`u-001`…`u-005`) e o histórico é simulado. É uma vantagem do tema: nada precisa ser anonimizado antes de entrar no contexto do modelo.

A única informação com alguma sensibilidade é o histórico de consumo, que em produção seria dado pessoal sob LGPD. Na Parte 1 ele é inventado; se o projeto crescer, o histórico não deve sair do banco para o contexto do modelo além do mínimo (hoje só a lista de títulos já vistos, sem datas nem frequência).

## 10. Espaço para o que ainda vem

- [x] **RAG (Parte 2):** as **avaliações de espectadores** do catálogo. Hoje elas estão como lista de strings em `streaming_catalog.json` e são passadas inteiras ao modelo. É exatamente o formato que não escala: com 500 títulos, passar todas as avaliações estoura a janela. Viram base vetorial, consultada por trecho relevante ao clima pedido.
- [x] **MCP (Parte 2):** `src/catalogo_db.py` vira servidor MCP. As 4 ferramentas já têm esquema JSON declarado em `ferramentas.py:ESQUEMA_FERRAMENTAS` — é esse esquema que migra.
- [x] **LangChain (Parte 2):** a orquestração do laço de `agent.py` (estado, orçamento, terminação). É a parte que hoje é código nosso e que a biblioteca resolve, liberando esforço para o refinamento em múltiplas trocas.
- [x] **Multiagente (Parte 3):** dois agentes. Um **curador**, que decide o clima e escolhe o candidato, e um **auditor**, que recebe a escolha e verifica se a evidência citada realmente sustenta a recomendação — hoje isso é só a validação de invariantes em código, que pega violação de regra mas não pega justificativa inventada.

## 11. O maior risco

**O risco real:** as tags de clima do catálogo são escritas por nós, e o casamento entre a frase do usuário e essas tags é por substring. Isso funciona com 9 títulos e tags que nós mesmos escolhemos. Com um catálogo real, ou as tags não existem, ou são de gênero, e o mecanismo inteiro deixa de funcionar — o sistema vira um buscador de palavra-chave com um LLM caro por cima.

**Plano B:** substituir o casamento por tag pelo casamento semântico sobre as **avaliações de espectadores**, que é o RAG da Parte 2. As avaliações existem em catálogo real (TMDB, IMDb) e descrevem clima — "a sensação de mal-estar é constante" — que é justamente o que nenhum campo estruturado carrega. Por isso o RAG da Parte 2 não é enfeite: ele é o que mantém o tema de pé fora do conjunto de teste.
