## 1. Os casos: o golden dataset v1

### Os embriões

Não temos exemplos de few-shot: o prompt é zero-shot de propósito, e o cabeçalho de `prompts/system.txt` explica que exemplos só enviesariam a escolha para os títulos do exemplo. Também não temos perguntas com resposta conhecida nem o par `recall` × fidelidade, porque o RAG não existe; `docs/base-de-conhecimento-v1.md` define fontes e corte, mas nenhuma pergunta de teste. Casos demonstrados da Parte 2 não existem. O único material aproveitável dela é o exemplo da etapa de verificação da evidência (`docs/arquitetura.md` §3), em que *The Leftovers* é rejeitado porque "a evidência fala do luto, não do mal-estar que a pessoa citou"; ele entra na pergunta 3.

O que entra de fato são os 5 casos de `dados/cases.json`, que são ao mesmo tempo os casos com gabarito do `src/verificador.py` e as tarefas fixas da comparação de modelos de `docs/modelos.md` §4. As quatro sondas do `--autoteste` (fora da assinatura, acima da classificação, repetida, título inventado) continuam servindo para provar que o nível determinístico pega o que diz pegar, mas não são casos do agente.

### A tabela

Os 14 casos novos são sintéticos, escritos por nós. Conferimos cada gabarito contra `dados/streaming_catalog.json` e contra o filtro de `buscar_candidatos`, para não repetir o `caso_simples` da v1, que pedia *Dark* (16+) para um perfil 14+ (`docs/estado-da-entrega.md` §2.2). Quando há mais de uma resposta válida, o esperado é o conjunto.

| # | Entrada (usuário, assinaturas, teto, referência, pedido) | Esperado | Origem | Classe | Por que o caso existe |
|---|---|---|---|---|---|
| 1 | `caso_simples`: `u-001`, Netflix, 16+, ref. *Severance*, "Curti muito Severance. Me indica algo parecido." | *Dark*, Netflix | embrião; gabarito impossível na v1, corrigido | caminho feliz | O piso. *The OA* também casa, mas `u-001` já o recusou. |
| 2 | `u-011`, Hulu e Disney+, 14+, ref. *The Office*, "Gostei de The Office, quero algo nesse clima." | *Only Murders in the Building*, Hulu ou Disney+ | sintético | caminho feliz | Caminho feliz fora da Netflix. *The Bear* está no Hulu, mas é 16+. |
| 3 | `u-012`, Netflix, 16+, sem referência, "Quero uma série de mistério para maratonar hoje à noite." | *Dark* ou *The OA* | sintético | caminho feliz | Mesmo pedido do caso 6, sem histórico: dois candidatos igualmente válidos. Mede a variação de título (pergunta 4). |
| 4 | `divergencia_usuario_vs_sistema`: `u-002`, Netflix e Prime Video, 14+, ref. *Severance*, "Quero algo leve e sem ficar pensando demais. Me lembra Severance?" | *The Office*, Netflix | embrião; erro observado no 3B | divergência | O caso que define o tema. O 3B recebeu *The Office* da ferramenta e devolveu `no_match` em 6 de 12 repetições. |
| 5 | `u-016`, Netflix e Prime Video, 14+, ref. *Dark*, "Vi Dark e fiquei tenso demais. Hoje quero algo leve pra rir." | *The Office*, Netflix | sintético | divergência | Segunda divergência, para a classe não depender de uma frase só. A referência está acima do teto e mesmo assim pode ser citada. |
| 6 | `nao_repete_recomendacao`: `u-005`, Netflix, 16+, sem referência, "Quero uma série de mistério para maratonar hoje à noite." | *The OA*, Netflix | embrião; nasceu do histórico que era gravado e nunca lido | filtros e histórico | *Dark* casa, mas já foi recomendado a `u-005`. |
| 7 | `u-001`, Netflix, 16+, sem referência, "Quero algo com mistério e meio surreal." | *Dark*, Netflix | sintético | filtros e histórico | O melhor candidato (*The OA*) foi **recusado**, não recomendado: testa o outro desfecho do histórico. |
| 8 | `u-006`, Netflix, 14+, sem referência, "Quero algo estranho e misterioso." | *The OA* (14+), Netflix | sintético | filtros e histórico | Borda: classificação igual ao teto tem de passar, e *Dark* (16+) tem de ficar de fora. |
| 9 | `nao_dispara_acao`: `u-004`, Prime Video, 10+, ref. *Severance*, "Estou com vontade de uma série intensa e estranha, tipo Severance, mas sem pagar nada extra." | `no_match`, nada gravado | embrião; corrige o `no_action` da v1, que mandava recomendar *Servant* | recusa | A resposta óbvia (*Severance*, no Prime) é 16+. |
| 10 | `u-007`, Hulu, 14+, sem referência, "Quero algo intenso e caótico." | `no_match`, nada gravado | sintético | recusa | Borda do outro lado: *The Bear* está na assinatura, mas um degrau acima do teto. Par do caso 8. |
| 11 | `u-009`, nenhuma assinatura, 16+, sem referência, "Quero uma série de mistério." | `no_match`, `reason` diz que não há assinatura | sintético | recusa | Borda: lista de assinaturas vazia. Pega quem sugere "o melhor do catálogo". |
| 12 | `u-010`, Netflix, 16+, ref. *The Leftovers*, "Amei The Leftovers. Quero algo melancólico, sobre luto." | `no_match`; *Dark* é erro | sintético | recusa | Erro inverso ao do 3B: se o agente troca o clima pedido por "mal-estar", a ferramenta devolve *Dark*. |
| 13 | `u-013`, Netflix, 16+, ref. *The Bear*, "Quero ver The Bear, me recomenda mesmo sem eu assinar Hulu." | `no_match`; *The Bear* é violação | sintético | recusa | O próprio usuário pede algo fora da assinatura, e a regra do domínio tem de vencer. |
| 14 | `u-014`, Netflix, 14+, ref. *The Queen's Gambit*, "Gostei de The Queen's Gambit, quero outra com essa determinação." | `no_match` | sintético | recusa | Borda: o único título com esse clima é a própria referência, que a busca exclui. |
| 15 | `registro_inexistente`: `u-003`, Netflix, 16+, ref. *O Enigma de Kessler*, "Amei O Enigma de Kessler, me indica algo parecido." | `no_match`, `missing_info` pede o nome | embrião | entrada inválida | A ferramenta devolve erro, e o agente tem de encerrar sem chutar um título parecido. |
| 16 | `u-001`, Netflix, 16+, ref. *Severence* (grafia errada), "Curti muito Severence, me indica algo parecido." | `no_match`, `missing_info` pede o nome | sintético | entrada inválida | Borda: grafia errada de título que existe. O prompt v2 proíbe substituir a referência; se o grupo passar a aceitar a correção, o gabarito muda em nova versão. |
| 17 | `u-015`, Netflix, 16+, sem referência, pedido vazio | `no_match`, `missing_info` pergunta o que a pessoa quer | sintético | entrada inválida | Borda: entrada malformada. A busca com clima vazio devolve `argumento_invalido`. |
| 18 | `u-017`, Netflix, 16+, sem referência, "Quero algo bom pra assistir." | `no_match`, `missing_info` pede o clima | sintético, da limitação de `docs/case.md` §5.3 | entrada inválida | Pedido vago, a fraqueza que o próprio case declara. |
| 19 | `u-008`, Netflix, 16+, sem referência, "Como vai estar o tempo amanhã em São Paulo?" | `no_match`, nada gravado; *Dark* é erro | sintético, do risco de `docs/case.md` §11 | entrada inválida | Fora do domínio, com armadilha: a busca casa clima por substring no texto do pedido, e "tempo" é tag de *Dark*. O código entrega *Dark* ao modelo, e quem tem de recusar é ele. |

São 19 casos em 5 classes: caminho feliz (3), divergência (2), filtros e histórico (3), recusa (6) e entrada inválida (5). Os casos de recusa somam 11, e os de borda são o 8, o 10, o 11, o 14, o 16, o 17 e o 19.

Quase todos os casos são sintéticos. Cinco são os embriões, quatro deles ligados a um erro observado no desenvolvimento (no agente, no modelo ou no próprio gabarito); os outros 14 foram escritos por nós, sobre um catálogo cujas tags também escolhemos, o que favorece o sistema. Nenhum vem de incidente real, porque ninguém fora do grupo usou o agente. Os reais virão do serviço no ar, na Aula 12: toda sessão grava pedido, contexto, trajetória e decisão, e toda semana vamos revisar cada `no_match`, cada recusa e cada "já vi essa". Os primeiros usuários de fora serão os 5 amigos que cronometraram a linha de base (`docs/case.md` §5.2). Um registro só vira caso quando duas pessoas do grupo concordam com o esperado, e entra com origem "incidente real" e data.

## 2. As propriedades esperadas, nível a nível

O que custa confiança são as invariantes e a escrita indevida: o usuário abre a plataforma e não acha o título, um perfil 10+ recebe um título 16+, ou um título some das próximas buscas porque foi gravado sem ser mostrado. Essas têm tolerância zero. O que custa tempo é o `no_match` indevido, como o do 3B: a pessoa volta a rolar o catálogo, e a linha de base medida é de 11,7 minutos por decisão. Um `reason` mal escrito, mas verdadeiro, é o erro mais barato.

| Nível | Propriedade esperada | Avaliação esperada | O que é falhar no seu domínio |
|---|---|---|---|
| Determinístico | a saída respeita o contrato | JSON válido, exatamente as 7 chaves, `status` e `confidence` nos valores permitidos, `no_match` com `title` e `platform` nulos, `reason` com no máximo 2 frases | resposta em prosa ou em cerca de markdown, e o código que consome o JSON quebra |
| Determinístico | status e título são os esperados | `status == esperado` e `title ∈ conjunto_esperado` | no caso 4, `no_match` com *The Office* na mão |
| Determinístico | as invariantes valem | `verificar_invariantes` contra o banco: o título existe, está em plataforma assinada, respeita o teto, não foi oferecido antes, e o `platform` informado está na assinatura | no caso 13, *The Bear* para quem só assina Netflix |
| Trajetória | consultou a referência antes de buscar | `consultar_titulo` aparece antes de `buscar_candidatos` sempre que há referência | busca pelo que o modelo "sabe" de *Severance*, sem ler o catálogo |
| Trajetória | só recomenda o que a busca devolveu | `title` está entre os candidatos de `buscar_candidatos` no mesmo trace | *Dark* certo no caso 1 sem nenhuma busca: acerto por acaso |
| Trajetória | não relaxa o pedido | depois de busca vazia ou `registro_inexistente`, nenhuma busca com outro clima e nenhuma escrita | no caso 12, nova busca com "mal-estar" e *Dark* recomendado |
| Trajetória | segue o pedido na divergência | nos casos 4 e 5, o argumento `clima` não contém tags da referência | busca por "mistério" porque o usuário citou *Severance* |
| Trajetória | termina pelo caminho curto | parada `resposta_final` e no máximo 4 chamadas de ferramenta (o caminho medido usa de 1 a 3) | a busca se repete até estourar o orçamento de 8 passos |
| Resultado | grava exatamente o que recomenda | 1 linha nova no `historico` com (`user_id`, `title`) se `recommendation`; 0 se `no_match` | `no_match` com *Dark* gravado, e *Dark* some das próximas buscas sem ter sido visto |
| Resultado | o histórico anterior fica intacto | as linhas de `historico_seed.jsonl` continuam iguais | a recusa de *The OA* por `u-001` some, e ele volta a ser oferecido |
| Juiz LLM | a evidência do `reason` sustenta a recomendação para o motivo que o usuário deu | rubrica binária, juiz validado (pergunta 3) | título certo, e o `reason` cita avaliação inexistente ou de outro clima |
| Juiz LLM | o `no_match` explica o motivo verdadeiro | rubrica binária, não validada na v1 | no caso 9, "não encontrei nada", sem dizer que o único título é 16+ |

O nível de resultado não é vazio porque o agente escreve: a escrita é reversível, mas um histórico errado muda todas as recomendações seguintes daquele usuário. Na Parte 2 ele ganha a idempotência do registro e o resumo de gosto gravado pelo agente de personalização.

## 3. O juiz, e como ele vai ser validado

A propriedade escolhida é "a evidência citada no `reason` sustenta a recomendação para o motivo que o usuário deu". É a mesma da etapa avaliadora da Parte 2, e é a que as invariantes não conferem: o `verificador.py` sabe se *Dark* está na Netflix, mas não sabe se a frase que justifica *Dark* é verdadeira nem se ela responde ao pedido.

### A rubrica

O juiz recebe o pedido, o clima descrito pelo usuário, o `reason` e a ficha do título no catálogo (tags de clima, sinopse e avaliações), e só julga saídas `recommendation`. Primeiro ele lista cada afirmação do `reason` sobre o título e marca se ela está na ficha; depois responde SIM ou NÃO.

**SIM** exige três condições juntas. Toda afirmação sobre o título está na ficha, literalmente ou em paráfrase fiel, e toda citação entre aspas existe como avaliação daquele título. Pelo menos uma afirmação fala do motivo que o usuário deu, e não só de gênero, plataforma ou classificação. E, quando o pedido diverge da referência, a evidência trata do clima pedido.

A resposta é **NÃO** quando qualquer afirmação não está na ficha, mesmo com as outras certas; quando o `reason` só fala de plataforma, classificação ou gênero; ou quando a evidência é verdadeira, mas de outro clima. Basta uma evidência certa para o SIM, e basta uma afirmação sem apoio para o NÃO; o número de citações não conta.

### Um exemplo de cada lado

SIM: a saída real do caso 1 em `logs/demo_runs.json`, *Dark* com "O clima de mal-estar constante e mistério é semelhante ao de Severance [...] como destacado nas avaliações: 'o clima de inquietação é o que chama atenção' e 'sentimento de que algo está errado o tempo todo'" (acentuado aqui; no log e no catálogo está sem acento). As duas citações são avaliações de *Dark*, `mal_estar` e `misterio` estão nas tags, e mal-estar é o clima pedido.

NÃO: uma saída possível do caso 12, *Dark* com "Tem o mesmo peso melancólico de The Leftovers; as avaliações dizem que 'o clima de inquietação é o que chama atenção'". A citação existe, mas fala de inquietação, e a ficha de *Dark* não tem melancolia nem luto, que foi o pedido. É o exemplo da arquitetura ao contrário: lá *The Leftovers* caía por falar de luto quando o pedido era mal-estar.

### A validação

Vamos rotular 60 saídas. Quarenta vêm da primeira rodada da suíte, sorteadas entre recomendações do 8B e do 3B (o 3B garante erros reais na amostra). Vinte são construídas: 10 `reason` longos, com citações corretas e uma afirmação sem apoio (esperado NÃO), e 10 curtos, com uma evidência certa (esperado SIM). Cada saída é rotulada por duas pessoas do grupo, sem ver o rótulo da outra, e o desacordo discutido vira o rótulo de referência.

Os 5 amigos da linha de base rotulam 20 dessas saídas, e vale a maioria entre eles. Isso mede concordância com espectadores comuns, que são o usuário do app, e não com especialistas; o especialista do domínio seria um curador ou crítico que conhece os títulos, e não temos acesso a nenhum. Se grupo e amigos concordarem em menos de 80% dessas 20, o defeito é da rubrica, que é reescrita antes de medir o juiz.

Decidido agora, antes de medir: o juiz só é adotado com concordância de pelo menos 85% com o rótulo de referência nas 60 saídas, kappa de Cohen de pelo menos 0,6, **e** NÃO em pelo menos 9 dos 10 `reason` longos com afirmação sem apoio. Abaixo disso, a propriedade continua conferida à mão, por amostra.

### O viés que mais ameaça este juiz

A verbosidade: um `reason` longo, com aspas e vocabulário de crítica, parece mais embasado que uma frase curta e certa. A rubrica decide por afirmação, então um texto longo tem mais chances de falhar, e não de passar; os 10 `reason` longos e errados medem esse viés diretamente; e o contrato limita o `reason` a duas frases, conferido no nível determinístico. Viés de posição não se aplica, porque o juiz não compara pares. A auto-preferência nós não conseguimos eliminar: a conta só roda a família Ministral (`docs/modelos.md` §2), então o juiz será o `ministral-14b-2512`, com temperatura 0. A validação contra rótulo humano é o que vai mostrar se esse viés aparece.

## 4. O ruído, e a regra que separa melhora de acaso

### De onde vem o não determinismo

**Amostragem.** A suíte **controla** a temperatura em 0,2, a mesma da produção, porque testar em 0 seria avaliar outro sistema, e **mede** o que sobra com repetições. Já sabemos que sobra: em três execuções iguais do 8B, o total de tokens variou até 8%, e o 3B acertou a divergência em 6 de 12. O id do modelo é fixo, e a latência é medida à parte, porque um pico como o de 26,4 s registrado em `docs/modelos.md` §4 não pode decidir uma comparação.

**Memória que cresce, já na Parte 1.** O `src/agent.py` constrói o banco uma vez e roda todos os casos sobre ele, acumulando gravações. Com repetições, isso quebra a suíte: na segunda repetição do caso 1, *Dark* já estaria no histórico de `u-001`, e o certo viraria `no_match`. A suíte **controla** essa fonte reconstruindo o banco antes de cada execução, com cada caso declarando seu histórico inicial.

**TMDB, na Parte 2.** Avaliações entram e a disponibilidade por região muda por contrato. A suíte de regressão **controla** essa fonte com respostas gravadas do TMDB, num retrato datado servido por ferramenta simulada; senão um caso falharia porque um título saiu da Netflix, e não porque o agente piorou. Uma rodada separada contra o TMDB ao vivo **mede** essa deriva, fora da regra de promoção.

**Resumo de gosto, na Parte 2.** É memória que muda entre sessões, e a suíte o **congela**: cada caso que depende dele traz o resumo escrito à mão na entrada, e há casos para conferir que o pedido do momento vence o resumo (`docs/arquitetura.md` §4). A conversa de várias trocas entra do mesmo jeito, com as respostas do usuário roteirizadas. O agente de personalização, que escreve o resumo, fica para uma avaliação própria.

### Quantas repetições

Dez por caso, 190 execuções por versão: cerca de 1,1 milhão de tokens (média medida de 5.668 por execução), uns US$ 0,16 no preço de 18/09/2026, e de 6 a 16 minutos. Um agente que acerta na moeda, como o 3B na divergência, passa 10 de 10 com probabilidade de 0,1%, então esse erro não escapa. Um erro de 10% por execução só é pego em cerca de 65% das vezes; esse é o limite de resolução, e sabemos disso.

### pass@k ou pass^k

`pass^k`. O agente grava no histórico, e uma recomendação fora da assinatura ou repetida quebra a confiança na primeira vez: acertar alguma das 10 não basta. Para invariantes e resultado, o critério é passar nas 10 repetições de todos os casos.

A escolha do título também usa `pass^k`, mas sobre o conjunto de respostas válidas. No caso 3, alternar entre *Dark* e *The OA* não é falha; a alternância é registrada, não penalizada. Nos casos de resposta única, `pass^k` é o que separa o 8B do 3B: no caso 4, o 3B tem `pass@12` igual a 1 e `pass^12` igual a 0. O `pass@k` fica como diagnóstico de uma versão que sabe fazer, mas não faz sempre.

### A regra de promoção (10/10/2026)

Escrita em 10/10/2026, antes de qualquer execução da suíte de 19 casos. A referência é a versão atual: prompt v2, `ministral-8b-2512`, `temperature=0.2`.

Antes da primeira comparação, rodamos a referência duas vezes (A/A). A diferença de taxa de acerto global entre as duas, contada por execução, é o ruído R. Se R passar de 5 pontos percentuais, subimos para 20 repetições antes de comparar qualquer coisa.

Uma mudança só é aceita se cumprir todas as condições. Nenhuma violação de invariante e nenhuma escrita indevida nas 190 execuções: uma basta para rejeitar, qualquer que seja o ganho. A taxa de acerto global sobe pelo menos 5 pontos percentuais (10 execuções em 190) ou o dobro de R, o que for maior; se a referência já passar de 95%, onde esse ganho não cabe, a exigência passa a ser levar pelo menos um caso a 10 de 10 sem tirar nenhum outro de 10 de 10. Nenhuma classe cai mais de 10 pontos percentuais, e nas classes recusa e entrada inválida nenhum caso perde o 10 de 10 que tinha. Nenhum caso isolado perde mais de 2 das 10 execuções. Depois de adotado o juiz, a taxa de SIM não cai mais de 5 pontos percentuais. E a latência mediana fica em até 5 s, o teto de `docs/modelos.md` §1.

Mudanças para baixar custo, como trocar o 8B pelo 3B, trocam a exigência de ganho por "a taxa global não cai mais que R" e "o custo por execução cai pelo menos 20%"; o resto vale igual. Com o que já medimos, o 3B seria rejeitado: errar 6 de 12 na divergência passa da queda máxima por caso.

A regra só muda numa nova versão datada deste documento, nunca depois de ver o resultado da comparação que ela decide.
