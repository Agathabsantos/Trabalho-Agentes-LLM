# Memória do agente de recomendação

## Contexto do caso

O agente do trabalho recomenda o próximo título para o usuário a partir do motivo do gosto, e não apenas do gênero ou do nome do título citado como referência. O sistema recebe um pedido em texto livre, verifica a conta do usuário, consulta o catálogo assinável, escolhe um candidato e grava o desfecho. A problemática central não é “escolher qualquer título”, e sim “lembrar o que o usuário gostou, o que já foi sugerido e o que já foi rejeitado” sem misturar contexto de uma sessão com contexto de outra.

O tema do projeto é o agente de recomendação de conteúdos em streaming, não o agente de prestação de contas. Por isso, a memória precisa preservar:

- a intenção da sessão atual;
- o histórico real do usuário em conversas anteriores;
- o resumo curto de gosto e rejeição;
- as regras de assinatura, classificação e perfil; e
- a resposta da sessão anterior, para não sugerir o mesmo item repetidamente.

A abordagem de memória precisa refletir esse domínio e não o domínio genérico de despacho ou análise financeira.

---

## Decisão 1 — Como o agente lembra

### 1.1 Os dois níveis, separados

No caso do app de recomendação, a memória de curto prazo e a de longo prazo têm papéis distintos. O problema é evitar que o agente “misture” estado da sessão atual com histórico acumulado e comece a recomendação a partir do texto errado, do caso antigo ou do perfil de outro usuário.

|  | curto prazo | longo prazo |
|---|---|---|
| o que é | a sessão corrente e o estado da conversa | o que atravessa sessões e usuários |
| conteúdo | intento do usuário, título de referência, perfil da conta, candidatos já testados, lista de sugestões recusadas, decisão pendente e mensagem atual | histórico de recomendações, resumo de gosto do usuário, regras do sistema e fatos estáveis sobre a conta |
| persistido como | checkpoint — um arquivo por sessão | índice vetorial, tabela de histórico e texto do system prompt |
| lido | uma vez, no início da retomada | por relevância, em cada volta do laço |
| acesso | por identificador de sessão | por chave do usuário ou por similaridade |
| ciclo de vida | termina junto com a sessão | acumula em várias interações |

No domínio do case, o checkpoint precisa guardar exatamente o que torna a sessão retomável sem reaplicar ação irreversível. O agente da Parte 1 grava apenas o histórico de recomendação e não compra nem assina nada; por isso o checkpoint guarda:

- `session_id` ou identificador da conversa;
- `user_id` e `perfil` ativo;
- referência do pedido (“gostei de Severance”), com o título citado e o motivo em texto livre;
- estado da missão atual: intenção do usuário, clima pedido e clima inferido;
- candidatos tentados, com o resultado de cada busca;
- lista de títulos já sugeridos ou recusados nesta mesma sessão;
- filtros de assinatura, classificação indicativa e plataforma disponível;
- decisão parcial produzida pelo modelo e a evidência que a sustenta;
- status da sessão: `em_andamento`, `resposta_final`, `no_match` ou `aguardando_humano`;
- resposta construída até o momento e motivo da parada.

Isso responde às três perguntas do exercício:

- a sessão pode ser retomada sem repetir efeito colateral? Sim, porque o checkpoint registre a sequência de buscas e a decisão atual; o sistema não reexecuta a gravação de histórico se já foi feita.
- uma aprovação humana pode chegar horas depois, de outro processo? Sim, porque a sessão pode ficar pendente por exigência de perfil ou confirmação de gasto e o estado completo continua disponível.
- um estado defeituoso pode ser carregado e reproduzido para depuração? Sim, porque o checkpoint serializa o estado da sessão inteiro e permite reproduzir a mesma decisão em laboratório.

### 1.2 O curto prazo: o orçamento da janela

A memória de longo prazo compete com o system prompt, o objetivo da sessão, o estado explícito da conversa e os trechos recuperados. No caso do app de recomendação, há cinco fontes competindo pela janela.

| Fonte | Teto (tokens) | Conteúdo | Regra de descarte |
|---|---:|---|---|
| system prompt | 2.000 | regras do produto, critérios de recomendação, invariantes de assinatura e limites de segurança | descarta instruções redundantes ou de baixa prioridade |
| objetivo e contexto da sessão | 1.500 | `user_id`, perfil, assinatura, título de referência e pedido do usuário | preserva o que orienta a decisão atual; remove contexto proveniente de outra conversa |
| trajetória da sessão | 3.000 | passos já executados, buscas, candidatos, erros e justificativas | elimina primeiro os passos mais antigos e menos relevantes |
| trechos recuperados | 4.000 | avaliações, metadados do catálogo e histórico relevante | descarta o item com menor score de relevância |
| memória de longo prazo | 2.500 | histórico do usuário, resumo de gosto e regras aprendidas | remove primeiro o dado mais antigo e menos útil para a decisão atual |

Quando o total estoura, a regra é: manter o objetivo da sessão, o estado atual e as evidências que influenciam a recomendação. O descarte não deve acontecer no fim do contexto, porque o trecho mais recente nem sempre é o mais importante; em um agente de recomendação, o “motivo do gosto” e o histórico do usuário geralmente têm mais valor do que o último texto do usuário sem contexto.

### 1.3 O longo prazo: as três memórias no case

No caso de recomendação, a memória de longo prazo é a base que permite aprender com as decisões anteriores e não repetir o mesmo erro em outras conversas.

| Tipo | O que guarda no case | Estrutura | Como é recuperada |
|---|---|---|---|
| episódica | histórico de recomendações e seus desfechos: título sugerido, motivo, plataforma, se o usuário aceitou, recusou ou já viu | índice por similaridade | consultada por similaridade sobre o contexto atual, como “user_id”, “título citado” e “motivo do gosto” |
| semântica | resumo do gosto do usuário, títulos rejeitados, preferências por clima, perfil e regras de conta | chave-valor | lida por chave (`user_id`, `perfil`, `assinatura`) para recuperar o resumo curto de gosto |
| procedural | regras operacionais do agente: sempre respeitar assinatura, nunca repetir item rejeitado, priorizar pedido do usuário sobre referência quando houver divergência | texto no system prompt | inserida em bloco fixo no início de cada execução |

A estrutura é diretamente funcional: a memória episódica precisa de similaridade porque o caso relevante é “algo parecido com o que o usuário já gostou”; a semântica precisa de chave porque o resumo do gosto do usuário é um dado estável por usuário; e a procedural precisa ser prompt porque é regra de operação do sistema, e não um fato pesquisado em banco.

### 1.4 Quem escreve, e o que não entra

A política de escrita é composta por três camadas:

- o agente decide se o registro é relevante para persistência;
- o código extrai o dado em formato estruturado; e
- o humano corrige apenas casos de regra de negócio ou exceção de política.

O volume por execução é limitado:

- episódica: até 1 registro por recomendação concluída, contendo título, motivo, plataforma, data e desfecho;
- semântica: até 1 resumo por usuário por rotina de personalização; o resumo é atualizado em lote, não por cada frase;
- procedural: no máximo 1 regra nova por execução, e só se validada em cenário real;
- checkpoint: 1 arquivo por sessão, sem adicionar ruído ao histórico do usuário.

O que o sistema não guarda é parte decisiva do desenho:

- dado sensível: nome do usuário, dado financeiro, credenciais, contato ou qualquer informação não necessária para a recomendação;
- conteúdo vindo de fora sem confirmação: avaliação de terceiros que não foi validada como evidência do catálogo ou texto bruto sem contexto;
- o que é derivável: o agente não guarda o catálogo inteiro em memória do usuário; ele guarda apenas o resumo e os registros relevantes para a decisão.

A regra geral é simples: o sistema guarda o que muda a recomendação, e não o que apenas enche a memória.

---

## Decisão 2 — Como o agente esquece

A memória do agente precisa esquecer de forma explícita. Sem isso, o sistema acumula dados antigos, recicla recomendação erradas e começa a decidir com contexto que já não tem valor. No caso do app de recomendação, as três causas de esquecimento são:

| Causa | O que aconteceu | O dado é apagado? | Quando decide |
|---|---|---|---|
| contradição | o fato mudou | não | na leitura |
| decaimento | o fato envelheceu | sim, ou é rebaixado | em rotina |
| remoção | o titular solicitou | sim, obrigatoriamente | sob demanda |

### 2.1 Contradição — o fato que mudou

O caso real tem um exemplo clássico: a pessoa cita Severance como referência, mas pede “algo leve”. A referência sugere um clima intenso e de mal-estar, e o pedido do usuário pede algo leve. O sistema precisa escolher qual informação vence. A regra do projeto é determinística: o pedido do usuário vence a referência citada quando o clima diverge. Isso é estabelecido em prompt e em regra de negócio, e não depende de o modelo “decidir a mão”.

A disciplina de desempate exige carimbo de tempo em todo fato relevante. A leitura faz `max()` sobre o campo de tempo para decidir qual versão do fato está vigente. Isso é importante porque o vetor de similaridade não representa anterioridade: diferentes registros podem ter conteúdo muito parecido e ainda assim representar situações diferentes. Em outras palavras, o embedding ajuda a encontrar o fato relacionado, mas não resolve temporalidade. A temporalidade precisa ficar explícita no dado.

Além disso, o descarte da versão antiga é registrado. Um episódio contraditório que foi descartado não pode ser silenciado; ele precisa aparecer no log como “descartado por temporalidade”. Caso contrário, o sistema parece ter ignorado o fato, mas o log não permite distinguir entre “não foi constatado” e “foi recuperado e rejeitado”.

### 2.2 Decaimento — o fato que envelheceu sem ser contradito

No caso do app de recomendação, o decaimento é especialmente importante para a memória episódica e para o resumo do gosto. Se o usuário gostou de uma série de clima “misterioso e tenso” há seis meses, isso pode ter relevância para a recomendação de hoje, mas não deve permanecer com peso igual ao de um gosto recente. O corte adequado é de 120 a 180 dias para episódios de recomendação e 90 dias para elementos de rejeição pontuais, conforme o nível de mudança do interesse do usuário.

A regra do sistema é:

- contas ou históricos antigos são rebaixados na ordenação;
- itens extremamente antigos são removidos do histórico ativo; e
- o resumo semântico do usuário continua sendo atualizado por rotina.

O efeito é importante: o dado não precisa ser apagado imediatamente, mas precisa perder relevância conforme o tempo. Isso evita que o sistema continue sugerindo títulos com base em gosto que já não domina o comportamento atual do usuário.

### 2.3 Remoção — o titular solicitou

A remoção sob pedido precisa cobrir todas as estruturas em que o identificador do usuário apareceu, e não apenas a memória semântica. No caso do app de recomendação, o titular é o usuário, e o identificador pode ter caído em:

- memória episódica: histórico de títulos sugeridos e decisões do usuário;
- memória semântica: resumo de gosto, rejeições e preferências por perfil;
- memória procedural: regras aprendidas que citam o usuário ou a sessão;
- checkpoint: arquivos de sessão que guardam `user_id`, perfil e título relevante;
- log: registros de execução, argumentos de ferramenta e retornos da conversa;
- metadados de indexação: campos de busca, vetores e estruturas auxiliares;
- respostas humanas: textos de confirmação ou justificativa que citam o usuário.

A verificação deve ser independente da remoção. O procedimento correto é:

1. localizar o identificador do usuário em todas as estruturas;
2. remover o registro do índice, do cache e dos arquivos físicos;
3. varrer as estruturas procurando o identificador novamente;
4. reconstruir o índice quando a remoção exigir; e
5. confirmar que não há mais ocorrências em checkpoint, logs, memórias, metadados e respostas.

Se a remoção exige reconstrução do índice inteiro, isso precisa ser explicitamente declarado. Essa regra preserva privacidade e custo e evita que uma memória “envenenada” continue viva até a próxima janela de manutenção.

### 2.4 O preço: o sistema deixou de ser reprodutível

A mesma entrada, com o mesmo modelo e os mesmos parâmetros, pode gerar uma resposta diferente amanhã porque a memória do usuário mudou. Isso não é falha e não deve ser tratado como bug. Ele é fruto do desenho do sistema: o agente é stateful, lembra e adapta a recomendação ao histórico. Em avaliação, isso significa que o ambiente do sistema não é apenas “a pergunta do usuário”; ele também é “o estado da memória naquele instante”.

Esse custo precisa ser registrado porque a aula 11 vai medir a recomendação sobre uma memória dinâmica. A avaliação não vai medir apenas a resposta correta, mas também a história acumulada do agente e a forma como ela altera a decisão.

---

## O que o agente não guarda — e o que ele perde quando perde

A parte mais importante do desenho não é o que guarda, mas o que rejeita. O agente do caso de recomendação não guarda:

- dados pessoais além do mínimo necessário para identidade do usuário e do perfil;
- histórico completo e irrelevante de todas as interações;
- textos de terceiros sem verificações de evidência;
- conteúdo derivável do catálogo, que pode ser recalculado sem custo;
- itens antigos que já perderam valor para a recomendação atual.

Quando o agente perde a memória, ele perde:

- a continuidade da conversa;
- o histórico de prefêrencias do usuário;
- a capacidade de evitar repetição e de refletir o que o usuário rejeitou;
- a consistência temporal da recomendação;
- o contexto necessário para decidir entre referência e pedido quando eles divergem.

Isso é o custo de projeto: um agente de recomendação é um sistema que lembra e esquece de maneira deliberada, e essa decisão precisa estar documentada para que privacidade, avaliação e manutenção sejam tratadas como parte da arquitetura e não como acidente de implementação.

---

## Resumo da decisão de projeto

A memória do agente do trabalho foi definida assim:

- o checkpoint guarda o estado da sessão atual e não o histórico do usuário;
- o curto prazo guarda o que a sessão precisa para agir de forma reprodutível;
- o longo prazo guarda episódios, fatos estáveis e regras operacionais;
- a escrita é controlada e limitada para não transformar o histórico em um arquivo morto;
- o esquecimento é arquitetural: contradita por tempo, decai por idade e sai por remoção sob demanda;
- a verificação da remoção é obrigatória e independente da operação.

Este documento é o rascunho direto do que a Parte 2 exige no §4: a decisão do projeto permanece explícita no domínio real do app de recomendação, e não em um caso genérico do curso.
