# Case — recomendação de próximo título com base no motivo do gosto

## 1. O problema

**Problema em uma frase:** um agente que identifica o motivo exato do gosto do usuário em um título e recomenda a próxima série ou filme disponível na conta, sem repetir itens e sem sugerir algo fora do perfil ou fora da assinatura.

**Quem sofre com ele hoje:** o usuário de streaming que quer decidir o que assistir sem passar longos minutos navegando no catálogo.

**Contexto de uso:** o sistema roda em um chat dentro do app de recomendação. O usuário descreve um título que gostou e o agente pergunta o que mais agradou nele. Antes do agente, a pessoa abre o catálogo, tenta buscar por gênero ou nota e recebe sugestões genéricas que não explicam por que foram escolhidas. Depois, o usuário decide aceitar ou rejeitar a recomendação. O domínio tem regras claras: o título precisa estar em plataforma que a pessoa assina; não pode repetir o que já foi sugerido ou assistido; e a recomendação precisa respeitar a classificação do perfil ou da sessão.

**O que acontece hoje sem ele:** a pessoa rola o catálogo, usa filtros de gênero e perde em média 14 minutos por decisão. O processo envolve navegação repetida, comparação manual entre plataformas e frustração quando a sugestão está em serviço fora da assinatura.

**Regras do domínio:**
- o título recomendado precisa estar em alguma plataforma assinada pelo usuário;
- não pode repetir recomendação anterior nem título já assistido;
- a recomendação precisa respeitar classificação indicativa e perfil da sessão;
- um gasto extra ou assinatura fora do pacote precisa ser confirmado pelo responsável pela conta.

**O que dá errado hoje:**
- a recomendação responde ao gênero, não ao motivo exato do gosto;
- a mesma sugestão volta em outras conversas;
- a sugestão aparece em plataforma que a pessoa não assina;
- a sessão em grupo ou perfil infantil recebe recomendação incompatível;
- a pessoa diz “gostei de Severance”, mas o que a agradou foi o clima de mal-estar, não o rótulo de suspense corporativo.

## 2. Usuários e como o agente conversa com eles

### 2.1 Perfis

| Perfil | O que ele quer | O que ele sabe | O que ele pode fazer |
|---|---|---|---|
| Usuário principal | decidir rápido o que assistir | sabe o que já gostou, mas nem sempre consegue explicar por quê | pede recomendação, aceita ou recusa, responde perguntas de refinamento |
| Responsável pela conta | evitar gasto extra e manter a conta dentro das regras | conhece a assinatura, perfil e restrições | aprova ou bloqueia recomendação paga ou incompatível |
| Pessoa assistindo junto | que a sugestão funcione para o grupo | sabe o que gosta em grupo, mas nem sempre informa isso de cara | aceita ou recusa a sugestão compartilhada |

**Usuário principal:** o usuário do serviço de streaming que quer uma decisão rápida.

### 2.2 Como é a interação

- Canal: chat dentro do app de recomendação.
- Quem começa: o usuário.
- Trocas: média de 3 a 6, até o sistema ter contexto suficiente.
- O que devolve: até 3 sugestões, com motivo, plataforma disponível e evidência curta.
- Como termina: se há opção compatível, a resposta é direta; se não há, o sistema responde que o catálogo assinado não bate com a intenção e pede refinamento.

### 2.3 Diálogo de exemplo

> Usuário: “Curti muito Severance. Me indica algo parecido.”
>
> Agente: “O que te prendeu mais em Severance: o mistério corporativo ou o clima de mal-estar constante?”
>
> Usuário: “O clima estranho.”
>
> Agente: “Nesse caso, Dark está na sua Netflix e combina com esse clima de estranhamento constante. As avaliações citam exatamente essa sensação de algo errado o tempo todo. Quer outra opção?”
>
> Usuário: “Só Dark por enquanto.”

### 2.4 Complexidade real de interação

- O usuário não informa de primeira o motivo do gosto; o sistema precisa descobrir isso com uma pergunta.
- Se o que o usuário diz contradiz o que o sistema encontra no catálogo, o sistema prioriza a evidência do catálogo e do histórico.
- O sistema decide que já sabe o suficiente quando consegue associar a intenção do usuário a uma recomendação com plataforma e histórico compatível.
- O sistema para e chama um humano quando há recomendação paga, perfil incompatível ou ação fora da assinatura. O responsável pela conta é quem confirma.

## 3. Workflow do agente

```text
1. ENTRADA      o usuário descreve o título e o pedido         [decide: CÓDIGO]
2. COLETA       carrega assinatura, perfil e histórico          [decide: CÓDIGO]
3. REFINAMENTO  pergunta o que agradou no título, se preciso   [decide: MODELO]
4. CONSULTA     busca candidatos compatíveis no catálogo      [decide: CÓDIGO]
5. TRIAGEM      descarta fora da assinatura, fora do perfil   [decide: CÓDIGO]
                e repetidos
6. ANÁLISE      compara a intenção da pessoa com a evidência  [decide: MODELO]
7. AÇÃO         devolve até 3 sugestões com motivo            [ESCRITA: não irreversível]
8. RETORNO      informa o usuário e para quando não há match  [decide: CÓDIGO]
```

**Quem decide:** passos 1, 2, 4, 5 e 8 são decisões de código; passos 3 e 6 são do modelo. Isso mostra que o sistema é um agente simples, não um workflow puro: a decisão de interpretar o motivo da preferência fica no modelo, mas a filtragem e a validação ficam em código.

**Escritas:** a única escrita relevante é o registro de decisão; ela é reversível em log e histórico. Caso exista ação irreversível, ela precisa de confirmação do responsável pela conta.

## 4. O sistema

**O que o sistema faz:** ele entende a intenção do usuário em linguagem natural, valida a assinatura, descarta candidatos inadequados e devolve uma recomendação com evidência curta.

**Nível de autonomia pretendido:** agente simples. Um roteador ou workflow não bastam porque a decisão central é interpretar texto livre e decidir, em tempo de execução, qual pista do título importa.

### Ferramentas

| Ferramenta | O que faz | Leitura ou escrita | Reversível | Contra o que ela conversa |
|---|---|---|---|---|
| catalog_search | busca candidatos no catálogo local | leitura | sim | catálogo de títulos e assinatura |
| check_availability | verifica quais plataformas estão disponíveis para a conta | leitura | sim | assinatura do usuário |
| record_decision | registra a recomendação e o desfecho | escrita | sim em log | histórico de recomendações |
| fallback_reasoning | compara a descrição do usuário com sinopse e avaliações | leitura | sim | texto livre e evidência do catálogo |

## 5. Justificativa de negócio

### 5.1 Por que um agente, e não software comum

A tarefa exige decisão em tempo de execução: a pessoa diz “gostei de Severance”, mas o que ela quer não está em um campo estruturado. O modelo precisa interpretar a linguagem natural, identificar o motivo do gosto e decidir se o candidato combina com a assinatura e com o histórico. Um formulário ou uma regra SQL simples não resolve porque o problema não é só “buscar um filme parecido” — é “entender por que a pessoa gostou e decidir se isso faz sentido no contexto dela”.

### 5.2 Ganho esperado

**Eixo escolhido: tempo por tarefa**

- Linha de base medida: em 10 tentativas simuladas, a pessoa levou em média 14 minutos e 10 segundos para decidir um novo título usando catálogo e busca manual.
- Alvo: 2 minutos por decisão.
- Conta: de 14,17 min para 2 min = -86% de tempo por tarefa.
- Volume: em 200 decisões por dia, isso representa 2.400 minutos economizados por dia.
- Ressalva: a estimativa é acadêmica e declarada como tal, com a linha de base medida em simulação local do problema.

**Ganho do negócio:** menos esforço de navegação e mais decisões rápidas sem que o usuário abandone o app.

**Ganho do usuário:** menos rolagem de catálogo, menos frustração e mais chance de começar a assistir logo.

**Tensão:** o negócio pode preferir manter a pessoa dentro do app o maior tempo possível, mas o usuário quer sair da tela e decidir rápido. Esse conflito é real e foi mantido explícito.

### 5.3 O que não vale como justificativa

- “moderniza o processo”
- “melhora a eficiência” sem número
- “reduz custos” sem linha de base e volume
- “usa IA de ponta”
- “os concorrentes já usam”

### 5.4 O outro lado da conta

- custo de rodar: estimado em poucos centavos de dólar por 100 execuções, conforme documentação de modelos;
- custo de construir: esforço de 4 pessoas em uma entrega de prova de conceito;
- o que se perde: uma recomendação ruim pode acontecer quando a intenção do usuário é ambígua; nesse caso, o custo é frustração e menor confiança no sistema.

## 6. Verificador e critério de sucesso

**Verificador:** a decisão é validada por três regras:
1. o título precisa estar disponível na assinatura;
2. não pode ter sido recomendado ou recusado antes;
3. a evidência textual precisa combinar com a intenção do usuário.

**Critério de sucesso:** em 4 cenários do domínio, o sistema deve acertar 3 de 4 casos e não recomendar título fora da assinatura nem repetir recomendação recusada.

## 7. Dados

Os dados são simulados, mas preservam a dificuldade do problema.

- **Casos de divergência:** usuário diz “quero algo leve”, mas a referência é Severance, mais intensa; o sistema precisa interpretar a intenção do usuário e não apenas o gênero.
- **Registro inexistente:** caso em que a referência ou o título pedido não existe ou não está disponível no catálogo.
- **Caso que não deve disparar a ação principal:** a conta do usuário não tem assinatura compatível, então o agente deve parar em vez de recomendar.

## 8. Dado sensível

Não há dado sensível pessoal, financeiro ou de saúde neste tema. Os dados usados são simulados e não entram no contexto do modelo.

## 9. Espaço para o que ainda vem

- [x] RAG: sinopses, avaliações e regras de uso, em formato textual e estruturado.
- [x] MCP: integração de catálogo e histórico pode virar servidor MCP na Parte 2.
- [x] LangChain: a orquestração pode entrar como camada de fluxo na Parte 2.
- [x] Multiagente: na Parte 3, pode haver um agente de histórico e outro de recomendação.

## 10. O maior risco

O maior risco não é “o modelo pode errar”; isso é premissa. O risco real é a intenção do cliente ser vaga demais e o sistema forçar uma recomendação sem evidência. Para isso, o plano B é: exigir refinamento, filtrar por assinatura e histórico e encerrar com no_match em vez de inventar uma resposta.
