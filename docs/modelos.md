# Análise de modelos

## 1. Eixos relevantes para este caso

Escolhemos os eixos que importam para a decisão do tema e não o leaderboard geral. O caso exige:
- tool calling e saída estruturada em JSON;
- raciocínio curto, mas não trivial, para decidir o motivo da preferência;
- custo baixo e previsível para um protótipo;
- latência aceitável, porque há alguém esperando a resposta;
- política de dados simples, sem expor informação sensível.

Por isso, os eixos centrais foram: suporte a tool calling/JSON, custo por milhão de tokens, latência, raciocínio e compatibilidade com API pública.

## 2. Candidatos

### Modelo 1 — GPT-4.1-mini
- Vantagens: forte estabilidade em saída estruturada, bom raciocínio em prompt curto e boa leitura de intenção de texto.
- Desvantagens: custo maior que modelos mais enxutos.
- Adequação: melhor para a etapa de decisão do motivo do gosto.

### Modelo 2 — GPT-4o-mini
- Vantagens: custo menor e decisão geralmente boa em prompts curtos.
- Desvantagens: menos robustez para contraste de intenção e menos previsibilidade do contrato JSON.
- Adequação: alternativa econômica, mas menos segura para a etapa decisória do caso.

### Modelo 3 — Mistral Small
- Vantagens: bom custo-benefício e compatível com base_url em providers do ecossistema OpenAI-compatible.
- Desvantagens: menor previsibilidade na inferência de motivações sutis e menor estabilidade em JSON.
- Adequação: viável para protótipo, mas menos convincente para a etapa mais importante do caso.

## 3. Conta de custo

A fórmula aplicada foi:

```
(tokens de entrada por chamada × chamadas por execução × preço de entrada)
+
(tokens de saída por chamada × chamadas por execução × preço de saída)
=
 custo por execução
```

Assumindo duas chamadas por execução, 1.200 tokens de entrada e 300 de saída por chamada, e preços aproximados de US$ 0,00015 por 1K tokens de entrada e US$ 0,00060 por 1K tokens de saída:

- entrada: 1.200 × 2 × 0,00015 = US$ 0,00036
- saída: 300 × 2 × 0,00060 = US$ 0,00036
- total por execução: US$ 0,00072
- custo por 100 execuções: US$ 0,072
- custo estimado para 20.000 execuções no semestre: US$ 14,40

Esse custo é compatível com uma prova de conceito, e a variação real de custo segue o número de chamadas e o volume de execução.

## 4. Verificação mínima

Usamos o mesmo prompt, os mesmos casos e a mesma estrutura de saída para comparar a aderência ao problema. A tabela abaixo sintetiza o benchmark mínimo aplicado ao protótipo do caso.

| Caso | Objetivo | GPT-4.1-mini | GPT-4o-mini | Mistral Small |
|---|---|---|---|---|
| caso simples | recomendar sem erro | acerta | acerta | acerta, mas menos estável |
| divergência | usuário quer algo mais leve e o sistema entende a intenção | acerta | acerta | ambiguamente classifica |
| registro inexistente | não inventar item | acerta | acerta | pode forçar uma resposta |
| caso fora da assinatura | não disparar recomendação principal | acerta | acerta | requer mais reforço |
| caso de perfil/controle | respeitar regra de conta e perfil | acerta | acerta | menos confiável |

Os três modelos passam no caso simples, mas o GPT-4.1-mini é o mais estável quando a decisão exige interpretar “o que a pessoa gostou de verdade” e não só um rótulo de gênero.

## 5. Decisão

**Modelo escolhido:** GPT-4.1-mini.

**Por quê:**
1. melhor aderência ao contrato de saída JSON;
2. melhor estabilidade para interpretar contraste de intenção;
3. custo aceitável para uma prova de conceito sem transformar o projeto em um problema de infraestrutura.

**Quando eu mudaria de ideia:**
- se o volume de execuções crescer e o custo por execução virar gargalo;
- se a IO do provedor ou a latência passarem a ser limites reais do produto;
- se o protótipo migrar para inferência local e a equipe quiser reduzir custo e depender menos de API pública.

## 6. Condição de mudança de decisão

A decisão muda se a equipe perceber que a qualidade da inferência não é suficiente para distinguir um caso ruim de um caso ambíguo. Nesse ponto, o projeto teria de reduzir a autonomia do agente ou mudar para um modelo mais estável, porque a etapa de interpretação da preferência é o ponto crítico da arquitetura.
