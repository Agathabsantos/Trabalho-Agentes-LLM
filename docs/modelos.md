# Análise de modelos

> Versão 2 — revisada em 19/09/2026.
> O que mudou: a tabela de comparação da §4 deixou de ser uma expectativa
> escrita à mão e passou a ser gerada por `src/benchmark_modelos.py`, a partir
> de execução real. Enquanto o benchmark não for rodado, a seção diz isso
> explicitamente em vez de apresentar resultados que não existem.

## 1. Os eixos, e por que estes

O objetivo aqui é **justificar uma escolha**, não catalogar o mercado. Os eixos abaixo foram escolhidos porque cada um decide alguma coisa no nosso caso; os demais foram descartados, e o porquê está dito.

| Eixo | Por que importa **neste** caso |
|---|---|
| **Tool calling** | Pré-requisito absoluto. O agente decide chamando `consultar_titulo`, `buscar_candidatos` e `registrar_recomendacao`. Sem tool calling nativo, não há agente — há um gerador de texto |
| **Saída estruturada** | O contrato de saída tem 7 chaves e é consumido por código. Uma resposta em prosa quebra o `verificador.py` |
| **Aderência a instrução negativa** | O prompt tem 5 proibições ("não recomende fora da assinatura", "não invente título"). O eixo real do nosso caso não é "o modelo é inteligente", é **"o modelo obedece a restrição quando a resposta óbvia a viola"** — é isso que o caso `nao_dispara_acao` mede |
| **Recuperação de erro de ferramenta** | O caso `registro_inexistente` devolve erro e testa se o modelo lê o `como_corrigir` ou se inventa um título parecido que ele conhece do treino |
| **Custo por milhão de tokens** | Multiplicado por 3 a 4 chamadas por execução — ver §3 |
| **Latência** | Há alguém esperando na frente da tela. Acima de ~5 s por execução, o chat perde para rolar o catálogo |

**Eixos descartados, e por quê:** *janela de contexto* — nosso maior prompt tem menos de 2.000 tokens, então qualquer candidato serve e o eixo não separa ninguém. *Multimídia* — o sistema é texto puro. *Onde roda* e *política de dados* — o §9 do `case.md` mostra que não há dado sensível, então nenhum candidato é eliminado por isso. Um eixo que não elimina ninguém não é critério de decisão.

## 2. Os candidatos

> **Por que estes três.** A lista original era GPT-4.1-mini, GPT-4o-mini e
> Mistral Small. Ao rodar o benchmark, a conta do grupo (Mistral, plano
> gratuito) não serviu nenhum deles — os GPT exigem chave OpenAI; `mistral-small`
> e `mistral-large` devolvem 429 e 403. Os três abaixo são os que a conta
> efetivamente roda, e formam uma escala de tamanho, que é o eixo que
> queríamos testar.


| | **Ministral 3B** | **Ministral 8B** | **Ministral 14B** |
|---|---|---|---|
| Id na API | `ministral-3b-2512` | `ministral-8b-2512` | `ministral-14b-2512` |
| Tool calling nativo | sim | sim | sim |
| Limite da conta (tok/min) | 1.300.000 | 625.000 | 937.500 |
| Limite da conta (req/s) | 12,50 | 3,13 | 0,50 |
| Custo relativo | o piso da escala | intermediário | o mais caro dos três |
| Por que está na lista | se o menor resolver, não há motivo para pagar mais | o meio da escala | o teto disponível: se o maior não resolver, o tema não fecha com esta conta |

Os três são compatíveis com a biblioteca `openai`, então trocar entre eles muda apenas `LLM_BASE_URL` e `MODEL_NAME` — nenhuma linha de código. Isso foi verificado por construção: `src/motores.py:construir_client` lê as duas variáveis e nada mais.

**O que esta troca custa à análise:** perdemos a comparação entre *provedores*
(OpenAI × Mistral), que era o desenho original. O que restou compara *tamanhos*
dentro de um provedor só. É uma comparação mais estreita, e a declaramos como
tal — mas é uma comparação **medida**, que é o que a rubrica pede, contra uma
tabela mais ampla que não teríamos como executar.

## 3. A conta de custo

```
custo por execução =
    (tokens de entrada  × chamadas por execução × preço de entrada)
  + (tokens de saída    × chamadas por execução × preço de saída)
```

### Preço de tabela

Consultado em **18/09/2026** em <https://mistral.ai/pricing/api> e conferido
em <https://docs.mistral.ai/inference/pricing>. As duas páginas batem.

| | Entrada (US$/1M tok) | Saída (US$/1M tok) | Fonte e data |
|---|---|---|---|
| Ministral 3B (`ministral-3b-2512`) | 0,10 | 0,10 | mistral.ai/pricing/api, 18/09/2026 |
| Ministral 8B (`ministral-8b-2512`) | 0,15 | 0,15 | mistral.ai/pricing/api, 18/09/2026 |
| Ministral 14B (`ministral-14b-2512`) | 0,20 | 0,20 | mistral.ai/pricing/api, 18/09/2026 |

> Os candidatos originais (GPT-4.1-mini, GPT-4o-mini) **não têm linha aqui** e
> isso é deliberado: eles saíram da lista na §2 por não rodarem nesta conta, e
> escrever o preço deles seria preço de modelo que não medimos.

**Uma particularidade que simplifica a conta:** nos três Ministral o preço de
entrada e o de saída são **iguais**. Isso torna a divisão entrada/saída
irrelevante para o custo, e é por isso que a conta abaixo pode usar o
`total_tokens` que o log registra, sem precisar separá-lo.

### Medição real, não estimativa

Números extraídos de `estado_final.tokens` em `logs/demo_runs.json` — execução de
19/09/2026 com `ministral-8b-2512`, a mesma que produz o 5/5 da §4.

| Caso | Idas ao modelo | Chamadas de ferramenta | Tokens |
|---|---|---|---|
| `caso_simples` | 4 | 3 | 7.251 |
| `divergencia_usuario_vs_sistema` | 4 | 3 | 7.328 |
| `registro_inexistente` | 2 | 1 | 3.258 |
| `nao_dispara_acao` | 3 | 2 | 5.147 |
| `nao_repete_recomendacao` | 3 | 2 | 5.357 |
| **Média** | **3,2** | **2,2** | **5.668** |

**Variação entre execuções.** Rodamos os mesmos 5 casos três vezes no mesmo
modelo: **26.202**, **28.311** e **28.341** tokens no total — até **8%** de
diferença. O número de idas ao modelo e de chamadas de ferramenta foi idêntico
nas três; o que varia é o comprimento do texto gerado. A conta abaixo usa a
execução que está no repositório. **Trate o custo como ordem de grandeza, não
como valor exato** — com três amostras não dá para afirmar mais que isso.

**A estimativa anterior errou pouco.** A v1 desta seção supunha ~1.500 tokens
de entrada e ~250 de saída por ida, × 3,2 idas = ~5.600 tokens por execução. O
real é **5.668**. E a contagem de 3,2 idas ao modelo, que era um *piso*
derivado do modo heurístico, saiu **exata** nas três execuções: o modelo
percorreu o mesmo caminho mínimo em todos os cinco casos.

### A conta

```
custo por execução = 5,668.2 tokens × US$ 0,15 / 1.000.000 = US$ 0.000850
```

| | Valor |
|---|---|
| 1 execução | US$ 0.000850 |
| 100 execuções | US$ 0.0850 |
| 200 execuções/dia (volume da §5.2 do `case.md`) | US$ 0.1700/dia |
| 1 mês (30 dias) | US$ 5.10 |
| 1 semestre (6 meses) | US$ 30.61 |

Isso confirma a ordem de grandeza declarada em `case.md` §5.3 ("centavos de
dólar por 100 execuções"): são **8.5 centavos** por 100 execuções.

**O que esta conta não cobre:** o custo das execuções que falham e são
repetidas, o custo do benchmark (três modelos × cinco casos, ~66k tokens no
total, ~US$ 0,01) e o crescimento de contexto que o RAG da Parte 2 vai trazer —
o §5 da §5 lista esse último como condição de reavaliar o modelo.

**Se a escolha migrar para o 3B** (condição 1 da §5), o preço cai para US$ 0,10/1M
e o custo por execução cai proporcionalmente, para cerca de **US$ 0.000567** —
um terço a menos, supondo o mesmo número de tokens.

## 4. A verificação mínima — 5 casos nos 3 candidatos

Executado em **19/09/2026**, com o mesmo prompt (`prompts/system.txt` v2), os
mesmos parâmetros (`temperature=0.2`) e os mesmos 5 casos de `dados/cases.json`.
Saída bruta em `logs/benchmark_modelos.json`; tabela gerada por
`src/benchmark_modelos.py`, não escrita à mão.

```bash
python src/benchmark_modelos.py --modelos ministral-3b-2512 ministral-8b-2512 ministral-14b-2512
```

| Caso | Esperado | ministral-3b-2512 | ministral-8b-2512 | ministral-14b-2512 |
|---|---|---|---|---|
| caso_simples | Dark | acerta | acerta | acerta |
| divergencia_usuario_vs_sistema | The Office | erra (no_match) | acerta | acerta |
| registro_inexistente | no_match | acerta | acerta | acerta |
| nao_dispara_acao | no_match | acerta | acerta | acerta |
| nao_repete_recomendacao | The OA | acerta | acerta | acerta |

| Modelo | Acertos | Violacoes | Tokens totais | Tempo total |
|---|---|---|---|---|
| ministral-3b-2512 | 4/5 | 0 | 24080 | 10.2s |
| ministral-8b-2512 | 5/5 | 0 | 28214 | 49.7s |
| ministral-14b-2512 | 5/5 | 0 | 28243 | 19.9s |

### Este benchmark rodou duas vezes, e a primeira estava contaminada

A primeira execução (18/09) deu **3B 3/5, 8B 5/5, 14B 5/5**. Os dois "erros" do
3B não eram respostas: eram `erro_do_modelo` — HTTP 400
`invalid_request_message_order`. A causa era **nossa**: `src/motores.py`
processava só a primeira tool call quando o modelo emitia várias em paralelo, e
o histórico ficava com N pedidos e 1 resposta. O 3B emite chamadas paralelas; o
8B e o 14B, nestes casos, não — por isso só o 3B quebrava.

Corrigimos o laço (uma fila que entrega as chamadas pendentes uma a uma, cada
uma com sua resposta — `MotorModelo._fila_de_chamadas`) e rodamos de novo. A
tabela acima é a **segunda** execução, com o defeito corrigido. Zero erros HTTP
nos três modelos.

### O que a correção revelou: o 3B tem uma limitação real que o bug escondia

Com o laço corrigido, o 3B sobe para **4/5** — mas o caso que ele erra agora, ele
erra **de verdade**. Em `divergencia_usuario_vs_sistema` a trajetória dele é:

```
passo 1  consultar_titulo   {"nome": "Severance"}                -> ok
passo 2  buscar_candidatos  {"clima": "leve e facil"}            -> candidatos: ["The Office"]
passo 3  FINAL: no_match — "O candidato mais próximo ('The Office') tem um clima
         sarcástico e cotidiano, mas não atende ao pedido de algo que evite
         pensamentos profundos."
```

Ele faz **exatamente as chamadas certas**, recebe **o candidato certo** — e se
recusa a recomendá-lo, porque "reinterpreta" o pedido depois de a ferramenta já
ter filtrado. Não é o erro que o caso foi desenhado para pegar (seguir o rótulo
de Severance em vez do pedido); é um erro de **excesso de cautela**: devolver
`no_match` com um candidato válido na mão.

Repetimos esse caso **12 vezes** no 3B com o laço corrigido: acertou em 6,
devolveu `no_match` em 6. **É uma moeda.** No 8B, o mesmo caso acertou em todas
as execuções que fizemos (3 do `demo_runs` + 1 do benchmark).

Isso corrige o que a primeira versão desta seção afirmava — que o 3/5 do 3B
"era bug nosso, não incapacidade dele". Era metade verdade: o **crash** era
nosso; a **incerteza** na divergência é dele, e só ficou visível quando o crash
saiu da frente.

### Latência: uma observação, não uma conclusão

Na segunda execução o 8B levou **26,4 s** em `caso_simples` e **15,3 s** na
divergência — contra 2 a 5 s em todas as outras execuções que fizemos (três
rodadas do `demo_runs`, com 1,9 a 4,8 s por caso). Nas execuções seguintes a
latência voltou ao normal. Registramos como pico transitório do provedor, com
**uma** ocorrência; a Parte 3 deve medir latência com mais amostras antes de
qualquer afirmação. A coluna "Tempo total" da tabela carrega esse pico.

### O que cada caso separa

| Caso | O que ele separa entre os modelos |
|---|---|
| `caso_simples` | o piso: se falhar aqui, o candidato está fora |
| `divergencia_usuario_vs_sistema` | segue o pedido do usuário ou o rótulo da referência que ele citou — **foi o caso que separou o 3B dos outros** |
| `registro_inexistente` | lê o `como_corrigir` da ferramenta, ou inventa um título do próprio treino |
| `nao_dispara_acao` | obedece à restrição quando a resposta óbvia a viola |
| `nao_repete_recomendacao` | usa o histórico que a ferramenta devolveu |

**Nenhum dos três violou invariante em nenhum caso.** Nenhum recomendou fora
da assinatura, acima da classificação, repetido, ou inventou título — inclusive
o 3B. O eixo em que os modelos se separaram foi **confiança na ferramenta**, não
obediência às regras do domínio.

**Cinco casos não são medição estatística**, e não é isso que se pede. O que se
pede é ter olhado a saída dos três modelos no nosso problema antes de escolher.

## 5. A decisão

**Modelo escolhido para a Parte 1: Ministral 8B** (`ministral-8b-2512`),
configurado em `.env` via `MODEL_NAME`.

**A escolha mudou por causa do benchmark.** A versão anterior desta seção
escolhia o GPT-4.1-mini, e dizia explicitamente que a escolha era *"provisória e
baseada em eixo de risco, não em medição"*. Agora há medição — duas rodadas, a
segunda com o laço corrigido — e ela decidiu em dois passos:

1. **O 14B não ganha nada do 8B.** Empatam em acerto (5/5), em violações (0) e
   em tokens (28.214 contra 28.243 — 0,1% de diferença). O 14B custa
   33% mais por token (US$ 0,20 contra 0,15). Pela condição 1 que já estava
   escrita aqui — *"o mais barato empata → troca imediata"* — o 14B está
   descartado.
2. **O 3B não empatou, e agora sabemos por quê.** 4/5, e o caso que perde é a
   divergência, com ~50% de acerto em 12 repetições. É o caso que o tema
   inteiro existe para resolver (§1 do `case.md`: "recomendar pelo motivo, não
   pelo rótulo"). Um modelo que acerta esse caso na moeda não serve, mesmo
   custando um terço a menos.

Latência do 8B nas execuções normais: **1,9 a 4,8 s por caso**, dentro do teto
de ~5 s da §1. Houve um pico isolado de 26 s (§4), registrado e não explicado.

**Em que condições mudaríamos de ideia:**

1. **O 3B passar a acertar a divergência de forma estável** — por exemplo, com
   um ajuste de prompt que o impeça de reinterpretar o pedido depois da busca.
   Vale tentar na Parte 2: se resolver, a troca é imediata e o custo cai um
   terço. Hoje, sem esse ajuste, ele está fora.
2. **Qualquer candidato falha em `nao_dispara_acao` ou `registro_inexistente`** →
   está eliminado, mesmo que acerte os outros três. São os casos onde o erro é
   caro. *Nenhum dos três falhou nestes dois casos em nenhuma das rodadas.*
3. **A latência passar de ~5 s por execução de forma consistente** → reavaliamos.
   O pico de 26 s foi uma ocorrência; se virar padrão, o 8B perde para o 3B,
   que foi o mais rápido nas duas rodadas.
4. **A conta ganhar acesso a modelos maiores** (`mistral-small`/`large` hoje dão
   429 e 403) → vale repetir o benchmark, porque a comparação atual é só entre
   tamanhos de uma família, não entre provedores.
5. **O volume crescer** e o custo por execução (§3) virar gargalo → migração para
   modelo local, aceitando perda de qualidade nos casos de divergência.
6. **A Parte 2 trazer RAG** e a janela de contexto crescer com trechos de
   avaliações → o eixo "janela de contexto", hoje descartado por não separar
   ninguém, volta a ser critério.

**O que esta decisão não prova.** Cinco casos, um provedor, uma família de
modelos, duas rodadas. Não é medição estatística e não sustenta afirmação sobre
qual modelo é "melhor" — sustenta apenas que, no nosso problema, com o nosso
prompt, o 8B resolveu os cinco casos nas duas rodadas, o 14B não trouxe ganho
que pagasse a diferença, e o 3B falha no caso central com frequência demais.
