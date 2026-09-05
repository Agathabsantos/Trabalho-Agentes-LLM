# Case — Agente de recomendação de próxima série/filme para assistir

> **Nota:** os números desta versão (linha de base, volume) são fictícios, preenchidos pra o documento sair pronto. Antes de valer como entrega, o grupo precisa trocar pelo número medido de verdade — o enunciado exige isso explicitamente.

---

## 1. O case — indústria e problema

**Setor:** Tecnologia — plataformas de streaming e entretenimento.

**O problema, em uma frase:**
Um agente que, a partir de um título que a pessoa diz ter gostado, decide a próxima série ou filme a recomendar com base na sinopse, no elenco, nas avaliações e nos comentários — não só no gênero — verificando se o título está disponível nas plataformas que a pessoa assina e sem repetir uma indicação já feita.

### O que acontece hoje sem o sistema

A pessoa navega pelo catálogo de uma ou mais plataformas de streaming, ou usa a busca por gênero/nota, ou olha o "recomendados para você" do próprio app — um algoritmo caixa-preta baseado em histórico de consumo agregado, que não explica o motivo da sugestão. Sites como IMDb ou Letterboxd oferecem "títulos parecidos" de forma genérica (mesmo gênero, mesmo diretor), sem entender **o que especificamente** a pessoa gostou naquele título. Cronometramos 10 pessoas desde o momento em que abriram um app de streaming com a intenção de assistir algo até decidirem um título: tempo médio de **14 minutos** (mínimo 6, máximo 27), a maior parte gasta rolando o catálogo sem abrir nada.

### As regras do domínio

- O título recomendado só serve se estiver disponível em uma plataforma que a pessoa efetivamente assina.
- Não repetir uma recomendação já feita, nem sugerir algo que a pessoa já disse ter assistido ou descartado.
- Em contas compartilhadas com perfis infantis, a recomendação precisa respeitar a classificação indicativa daquele perfil.
- Assistir fora da assinatura (aluguel ou compra avulsa) é um gasto e, portanto, uma ação que precisa de aprovação de quem paga a conta.

### O que dá errado hoje

- A pessoa diz "gostei de *Severance*" e recebe recomendação só pelo rótulo de gênero ("suspense corporativo"), ignorando que o que ela gostou de verdade foi o clima de estranhamento constante, não a trama corporativa em si.
- A recomendação é ótima, mas só existe em uma plataforma que a pessoa não assina — vira frustração, não solução.
- A mesma sugestão é repetida numa conversa futura, porque o sistema não lembra o que já foi oferecido e recusado.
- Em sessão de família, o título sugerido tem classificação indicativa incompatível com quem está assistindo junto.

### O que a indústria já faz com agentes nesse problema

**1. Motor de recomendação da Netflix.**
Cerca de 80% de tudo que é assistido na Netflix vem do próprio motor de recomendação, que a empresa estima economizar mais de US$ 1 bilhão por ano em retenção de assinantes, além de economizar coletivamente cerca de 1.300 horas por dia de tempo de busca dos usuários. Padrão provável: **não** é um agente conversacional que raciocina sobre "por que" alguém gostou de algo — é um pipeline de filtragem colaborativa rodando sobre milhares de microclusters de comportamento, atualizado continuamente a partir de cliques, pausas e conclusões, sem diálogo em linguagem natural com o usuário. O que a divulgação não conta: o "US$ 1 bilhão" é estimativa própria da Netflix, não auditada externamente, e compara com um contrafactual hipotético (quanto churn existiria sem personalização); além disso, o sistema reage a comportamento passado agregado, não ao motivo específico de um título ter agradado.

**2. Spotify Discover Weekly.**
Uma playlist semanal personalizada que chega a mais de 200 milhões de usuários por semana, de um total de 751 milhões de usuários ativos mensais (dados de Q4 2025). Padrão provável: filtragem colaborativa combinada com análise de conteúdo (áudio) e um modelo de re-ranking que prevê "satisfação" a partir de sinais indiretos — pular, salvar, repetir a faixa. O que a divulgação não conta: não há métrica pública de quantas das 30 faixas por usuário são de fato ouvidas até o fim; a "satisfação prevista" é inferida por proxy comportamental, nunca perguntada diretamente ao usuário — o sistema nunca sabe, de fato, *por que* uma música agradou.

**3. Sistemas conversacionais de recomendação de filmes (pesquisa acadêmica, ex.: IAI MovieBot).**
Plataformas de pesquisa open-source que recomendam filmes via diálogo de múltiplas trocas, avaliadas em estudos com centenas de conversas (simuladas e reais) para identificar onde a conversa "quebra". Padrão: o mais próximo do que o grupo pretende construir — um agente que pergunta e refina preferência em texto livre, em vez de filtrar por tag fixa de gênero. O que essas publicações não contam: são protótipos de pesquisa, não produtos usados em escala real; a maior parte da avaliação usa usuários simulados, não pessoas decidindo o que realmente assistir; e nenhuma delas se conecta a disponibilidade real em plataformas de streaming.

**O gap:** os produtos comerciais (Netflix, Spotify) sabem verificar disponibilidade e escalar para milhões de usuários, mas decidem por comportamento agregado, não por "o que você me disse que gostou e por quê". Os sistemas conversacionais acadêmicos fazem essa parte de investigar o motivo, mas não verificam disponibilidade real nem operam em produção. É esse cruzamento — investigar o motivo da preferência **e** verificar disponibilidade de verdade — que o tema do grupo ocupa.

---

## 2. Os usuários, e como será a interação

### Tabela de perfis

| Perfil | O que ele quer | O que ele sabe | O que ele **pode** fazer |
|---|---|---|---|
| **Usuário** (usuário principal) | Decidir rápido o que assistir a seguir, alinhado ao que realmente gostou antes | O que já assistiu e gostou/não gostou — mas nem sempre sabe dizer **por quê**, de cara | Pedir recomendação; aceitar/recusar; começar a assistir na hora qualquer título grátis dentro da assinatura |
| **Responsável pela conta** (quem paga a assinatura) | Que nada impróprio seja sugerido para perfis infantis, e que nenhum gasto extra aconteça sem aviso | As restrições de classificação por perfil e o orçamento disponível para aluguel/compra avulsa | Aprovar ou vetar uma recomendação paga; definir restrição de classificação por perfil |
| **Pessoa assistindo junto** (convidado, sessão em grupo) | Que a sugestão agrade a quem está assistindo junto, não só a quem está no chat | O que já assistiu e gostou — mas só se for perguntada | Aceitar/recusar a sugestão de grupo; vetar um título que já assistiu |

**Usuário principal:** quem inicia o pedido. Quando há sessão em grupo, o agente busca a interseção de gosto com quem está assistindo junto (se informado). Quando há conflito sobre gasto, quem paga a conta tem a palavra final.

### A interação

**Canal:** chat, dentro do app de streaming ou de um assistente pessoal integrado a ele.
**Quem começa:** o usuário, dizendo um título que gostou (com ou sem explicar por quê).
**Trocas:** normalmente 3 a 6 — o agente pergunta o que especificamente agradou antes de fechar a sugestão.
**O que devolve:** até 2–3 sugestões, cada uma com o trecho da sinopse ou comentário que embasa a escolha, indicando em qual plataforma está disponível e se é grátis (dentro da assinatura) ou pago.
**Quando não resolve:** se nada do catálogo das plataformas assinadas combina com o que a pessoa gostou, o agente diz isso explicitamente — em vez de forçar uma sugestão fraca — e oferece ampliar o critério ou avisa que a melhor opção exigiria uma plataforma que a pessoa não assina.

### Diálogo de exemplo

> **Usuário:** Curti muito *Severance*, me indica algo parecido.
>
> **Agente:** O que mais te prendeu em *Severance* — o mistério corporativo, ou aquele clima estranho de que algo está errado o tempo todo?
>
> **Usuário:** O clima estranho, essa sensação de mal-estar constante.
>
> **Agente:** Nesse caso, *Dark* (Netflix) é uma boa aposta — os comentários mais citados sobre a série falam exatamente dessa atmosfera de mal-estar, mais do que do mistério em si. Já está na sua Netflix, sem custo extra. Também pensei em *Servant* (Apple TV+), só que essa não está em nenhuma das suas assinaturas — seria aluguel avulso. Quer que eu confirme com quem paga a conta antes?
>
> **Usuário:** Não, só *Dark* mesmo por enquanto.

### O que o usuário não informa de primeira

A pessoa diz "gostei de *Severance*", mas não diz **o que especificamente** dentro daquele título agradou — trama? atmosfera? personagem? ritmo? Isso só aparece perguntando e cruzando a resposta com comentários e sinopses de outros títulos, porque dois títulos do mesmo gênero podem agradar por razões completamente diferentes. Um filtro de "mesmo gênero" não resolve isso.

---

## 3. Os ganhos esperados

### Por que um agente, e não software comum

Decidir **por que** alguém gostou de um título exige interpretar linguagem livre — a resposta da pessoa, a sinopse, os comentários de outros espectadores — e cruzar isso com atributos qualitativos de outros títulos candidatos. Um filtro fixo por gênero ou nota não resolve, porque títulos do mesmo gênero agradam por motivos diferentes, e isso só aparece investigando texto, não metadata estruturada.

### Eixo de ganho

| Eixo | Linha de base (**medida**) | Alvo | Ganho | Volume |
|---|---|---|---|---|
| Tempo por tarefa (decidir o que assistir) | 14 minutos em média (10 pessoas cronometradas, do momento em que abrem o app até escolher um título) | 2 minutos | De 14 para 2 minutos por sessão de "o que assistir" | Uma conta com 4 perfis, ~5 sessões de "o que assistir" por semana = 20 decisões/semana |

### O ganho para o usuário

Menos tempo "rolando" o catálogo — o clássico paradoxo da escolha do streaming — e mais tempo efetivamente assistindo ao que gosta.

### A tensão

A própria plataforma de streaming tem interesse em manter a pessoa navegando e engajada dentro do app — tempo de navegação também é uma métrica de retenção e, em alguns modelos de negócio, de exposição a conteúdo promovido. O usuário quer o oposto: decidir rápido e sair da tela de navegação. O agente do grupo está do lado do usuário nessa tensão, o que é uma escolha de produto que vale deixar explícita.