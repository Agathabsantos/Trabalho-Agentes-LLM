# Base de Conhecimento do Agente — versão v1

## Contexto e escopo

Esta versão v1 define a base de conhecimento de um agente de recomendação de próxima série ou filme. A decisão de projeto é simples: o agente não deve depender do “senso comum” do modelo para saber o que a pessoa gosta, nem para decidir se um título está disponível na assinatura; ele precisa buscar essas informações no conjunto certo de fontes e misturar isso com o histórico real do usuário.

O ponto de arquitetura é separar duas coisas:

- conhecimento de recomendação e interpretação de gosto, que entra no índice semântico ou no estado da conversa;
- dados de usuário, histórico, assinatura e disponibilidade, que entram como consulta estruturada e filtro de metadado.

A base de conhecimento não é um catálogo completo do universo de filmes e séries. É o conjunto de fontes que responde a perguntas do tipo “o que a pessoa gostou de verdade?”, “esse título está dentro do que ela assina?”, “esse candidato ficou fora da classificação do perfil?” e “já foi sugerido ou recusado antes?”.

---

## 1. Qual informação especializada o agente precisa, e por que ela não está no modelo

### 1.1 Informações que o agente precisa ter e que o modelo não possui

| Informação | Por que não vem do modelo | Tipo de razão |
|---|---|---|
| histórico real de títulos assistidos e descartados do usuário | o modelo não conhece o comportamento do usuário nem o que ele já viu, aceitou ou recusou | privado |
| plataformas de streaming assinadas pelo usuário | isso é um dado de conta e muda por assinatura, região e perfil | privado / recente demais |
| classificação indicativa ativa por sessão ou perfil | a restrição pode mudar com quem está assistindo e com o perfil do usuário | privado |
| lista de recomendações anteriores e desfechos da conversa | o modelo não tem memória do histórico do app nem do que foi rejeitado antes | privado |
| motivo específico da preferência do usuário | a pessoa costuma dizer “gostei de Severance”, mas não explica de forma estrutural por que gostou; isso é extraído da conversa | específico demais |
| disponibilidade real por região e plataforma | a disponibilidade muda conforme assinatura, país e agenda do catálogo | recente demais |
| comentários e avaliações de espectadores sobre clima, atmosfera e sensação | o modelo pode generalizar, mas nem sempre identifica a pista exata da preferência do usuário | específico demais |

### 1.2 O que não precisa entrar no índice

O agente não precisa indexar o que o modelo já domina de forma genérica. Exemplos:

- noções gerais sobre gênero, trama e linguagem cinematográfica;
- explicações genéricas sobre “clima, tensão, suspense, drama”, sem contexto do usuário;
- definição de termos como “thriller”, “sci-fi”, “comédia de situação”, sem relação com o que a pessoa gostou de verdade;
- informação amplamente conhecida sobre filmes e séries muito populares, quando o que importa é a decisão específica do usuário.

Se o agente consegue responder “isso é geralmente mais psicológico ou mais de ação” sem consultar nada, essa informação não deve entrar no índice. O valor está no detalhe que combina com a pessoa, com a sessão e com a assinatura.

### 1.3 Decisão de projeto: o que o agente precisa saber e o que pode ser consultado em sistema

O agente precisa saber o motivo do gosto da pessoa e o contexto de acesso do título. Ele não precisa memorizar tudo do universo de filmes e séries, nem o histórico completo da conta em uma base textual.

Exemplos de informação que não entram no índice semântico:

- títulos já marcados como assistidos;
- lista de rejeições da conversa atual;
- perfil de classificação indicativa vigente;
- plano de assinatura, região e plataformas ativadas;
- código do título no TMDB e status de disponibilidade;
- histórico de sugestões aceitáveis e recusadas.

Esses elementos são resolvidos por consulta estruturada, com filtro por usuário, sessão, região e metadados do título.

---

## 2. Onde esses dados estão, e em que estado

### 2.1 Fontes principais

| Fonte | Onde vive | Formato | Dono | Frequência de mudança | Acesso |
|---|---|---|---|---|---|
| TMDB metadata de títulos | API TMDB | JSON / endpoint estruturado | equipe de produto / dados externos | diária ou em atualização do catálogo | sim, via API |
| comentários e avaliações de espectadores | TMDB | JSON / texto bruto de avaliações | terceiros / API TMDB | frequente | sim, via API |
| plataformas de streaming por título | TMDB Watch Providers | JSON estruturado | terceiros / fornecedora do catálogo | variável | sim, via API |
| histórico do usuário | banco próprio do app | banco relacional / tabela estruturada | produto / back-end | em tempo real | sim |
| assinatura do usuário | banco de contas e perfis | tabela estruturada | produto / billing | por alteração do plano | sim |
| classificação indicativa por perfil | banco de sessão/perfil | tabela estruturada | produto | por mudança do perfil | sim |
| conversa com o usuário | base de chat / log de sessão | texto em fila ou banco | produto | em tempo real | sim |

### 2.2 Estado real das fontes

A maior parte da informação relevante está em dados estruturados e em APIs públicas de catálogo. A recomendação não depende de “conhecimento em cabeça de alguém”; depende de fontes rastreáveis, instantâneas e verificáveis.

- A API TMDB é a fonte de catálogo e de evidência textual do candidato.
- O banco do app é a fonte do histórico real da pessoa e das decisões do agente.
- O banco de contas e perfis é a fonte de assinatura, classificação e região.
- A conversa do usuário é a fonte do motivo de gosto, que precisa ser extraído em tempo real.

### 2.3 Acesso e risco de dependência

A fonte crítica que poderia bloquear o projeto seria a indisponibilidade do TMDB ou a ausência do histórico do usuário. Mas o caso ainda é viável: a API é acessível e a base do usuário existe no próprio app. Não listamos nenhuma fonte sem acesso real. O único cuidado é a região e as plataformas de streaming: a disponibilidade muda por país e por contrato, então a verificação precisa acontecer no momento da recomendação.

Se houver dados sem estrutura ou texto em PDF/escaneado, isso não é o núcleo do caso. Este projeto se apoia em API e banco, e não em documentos de texto longo. Se a operação quiser armazenar uma política interna de recomendação, essa parte pode ser documentada em markdown, mas não é a principal fonte de decisão.

---

## 3. O que vai para o índice — e o que não vai

### 3.1 O que entra no índice

O índice do agente não precisa ser um “catálogo inteiro do TMDB”. Ele deve conter o material que melhora a decisão do agente em tempo de conversa:

- política de recomendação do produto: não repetir títulos, não sugerir fora da assinatura, respeitar classificação indicativa, priorizar evidência textual;
- FAQ interna do produto: regras de exceção, escopo de recomendação, limites de conversa, respostas do app;
- snippets de avaliação e sinopse dos candidatos realmente pesquisados na conversa;
- histórico de gosto do usuário resumido em texto, quando houver;
- contexto de perfil e sessão (assinaturas, classificação, região, títulos já rejeitados).

Volume estimado:

- 1 a 5 documentos de política/regras do produto;
- 10 a 50 itens de FAQ/decisão de produto;
- em cada sessão, dezenas de snippets de avaliação e detalhes do candidato;
- em uma conversa, o índice operacional de contexto costuma ficar em centenas de tokens, e não em milhões.

Essa escala é pequena. Com poucos blocos por sessão, um vetor em memória ou um índice leve local é mais do que suficiente. Não há necessidade de um banco vetorial massivo para essa etapa.

### 3.2 O que fica de fora

Não entram no índice:

- catálogo completo de todas as séries e filmes do mundo como texto livre;
- avaliações do TMDB em massa sem filtro de relevância;
- histórico bruto de todos os usuários do app como documento textual;
- dados de assinatura e perfil em texto livre;
- registros de assistidos que são apenas fruto da sessão, sem necessidade de semântica.

Essas informações pertencem a dados operacionais e devem ser consultadas por filtro e chave, não por busca semântica.

### 3.3 O que se resolve por consulta estruturada

A regra importante é esta: se a resposta depende de igualdade, faixa, região, assinatura, identificação do título ou restrição por perfil, ela não é recuperação por cosseno. É filtragem e consulta estruturada.

Exemplos:

- “qual título a pessoa já viu?” → consulta ao histórico do usuário;
- “quais candidatos estão na Netflix do Brasil?” → filtro de plataforma e região;
- “qual a classificação indicativa máxima da sessão?” → consulta ao perfil;
- “esse título já foi sugerido nessa conversa?” → filtro de histórico da sessão;
- “qual o desfecho do título X para o usuário?” → banco de recomendações.

Em outras palavras: se a pergunta precisa de usuário, assinado, região, classificação, ou identificador do título, o caminho correto é filtro estruturado, não similaridade.

### 3.4 O que entra no vetor e o que fica em tabela

| Tipo de informação | Modo de acesso | Observação |
|---|---|---|
| política de recomendação e FAQ | busca semântica + filtro | entra no índice |
| snippets de sinopse e avaliação de candidatos | busca semântica + filtro | entram no contexto da sessão |
| resumo de gosto do usuário | metadado + texto resumido | pode ser resultado de processamento estruturado |
| títulos assistidos e rejeitados | consulta estruturada | não é busca semântica |
| plataformas e assinatura por usuário | consulta estruturada | não é texto livre |
| classificação indicativa por perfil | consulta estruturada | filtro obrigatório |

---

## 4. A estratégia de chunking

### 4.1 Estrutura documental e corte natural

Os textos aqui não são todos do mesmo tipo. O agente lida com documentos de política, avaliações e contexto do usuário, e cada um pede um corte diferente.

#### a) Política e FAQ do produto

- Unidade natural: regra, regra de exceção e item de FAQ.
- Corte recomendado: por item, preservando o título e a regra aplicada.
- Motivo: cada item da política responde uma decisão clara. Se um item depende do anterior, esse contexto precisa permanecer junto.
- Metadado: tipo de regra, país/serviço, vigência, perfil afetado, status.

#### b) Comentários e avaliações de espectadores

- Unidade natural: comentário individual ou trecho de avaliação.
- Corte recomendado: por comentário completo, com destaque para a frase que menciona clima, tensão, humor ou personagem.
- Motivo: a avaliação deve ser útil como evidência; um comentário cortado ao meio perde a razão da recomendação.
- Metadado: título, plataforma, nota, tipo de sentimento, contexto da opinião.

#### c) Histórico do usuário e contexto da sessão

- Unidade natural: registro individual de recomendação, resposta da pessoa e desfecho.
- Corte recomendado: não é um chunk de texto livre, e sim registro estruturado.
- Motivo: a decisão do agente depende de metadados e de identificadores do usuário, do título e do resultado, não de semântica livre.
- Metadado: usuário, título, motivo, desfecho, data, sessão, plataforma.

### 4.2 Quando não houver unidade natural

Quando o contexto não tem estrutura clara, o corte será por contagem de caracteres, mas com foco em manter sentido e evidência.

- tamanho sugerido: 400 a 1.000 caracteres por chunk;
- sobreposição: 60 a 120 caracteres;
- motivo: preserva o que a pessoa gostou e o trecho da avaliação que sustenta a escolha, sem misturar opiniões que não dizem nada sobre o motivo da preferência.

O critério único é: o chunk precisa fazer sentido sozinho. Se ele depende de uma frase anterior para “explicar o que o usuário gostou”, ele está mal cortado.

### 4.3 Metadados essenciais por chunk

Cada chunk deve carregar metadados além do texto, e esses metadados são a ponte para o filtro estruturado:

- usuário_id;
- sessão_id;
- título_id;
- plataforma_assinada;
- região;
- classificação_indicativa;
- tipo_recomendacao;
- motivo_extraido;
- desfecho (aceita, recusa, já assistiu);
- data_da_decisao.

Isso permite responder:

- “qual a recomendação mais forte para o usuário X?” → filtro por usuário e contexto;
- “quais títulos já foram rejeitados nessa sessão?” → filtro por sessão;
- “esse candidato está disponível para a conta do usuário?” → filtro por plataforma e região;
- “a evidência fala do clima, e não do enredo?” → filtro por motivo e tipo de comentário.

### 4.4 Estratégia final

A estratégia de chunking deste v1 é híbrida, e isso é essencial. O agente não pode aplicar uma única regra para todo tipo de dado. A política do app e a FAQ exigem corte por item; as avaliações de usuário exigem corte por comentário; o histórico do usuário e a assinatura são metadados estruturados e não chunks textuais. O projeto precisa combinar recuperação por contexto com filtros de dados operacionais e não forçar tudo em uma mesma lógica de busca.

---

## Conclusão

A base de conhecimento v1 do agente deve ser pequena, específica e rastreável. O coração do valor não está em indexar o mundo inteiro de filmes e séries; está em decidir, para cada usuário, o que ele gosta de verdade, o que já foi sugerido, o que ele tem acesso e o que a sessão permite. A resposta correta vem de uma combinação de contexto textual, histórico e filtros estruturados.

Isso evita três erros comuns:

1. indexar informação que o modelo já sabe por tendência geral;
2. tratar histórico do usuário e disponibilidade como semântica livre;
3. usar uma estratégia única de chunking para todos os tipos de dado.

A v1 está certa em ser uma primeira aproximação, porque ela deixa visível exatamente o que precisa mudar quando o produto real e o corpus de uso forem descobertos. A base de conhecimento não existe para “saber tudo”; existe para apoiar a decisão correta do próximo título.
