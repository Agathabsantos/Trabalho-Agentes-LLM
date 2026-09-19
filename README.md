# Trabalho-Agentes-LLM — Parte 1

## Integrantes
- Agatha Barbosa Marinho dos Santos
- Bruna Kinjo Luiz Pinto
- Kayke Ahrens Biscegli
- Matheus da Silva Marini

## Problema em uma frase
Um agente que identifica o motivo real do gosto do usuário em um título e recomenda a próxima série ou filme disponível na conta, sem repetir itens e sem sair do perfil ou da assinatura.

## Como rodar
1. Clone o repositório e entre na pasta do projeto.
2. Crie o ambiente virtual:
   `python3 -m venv .venv`
3. Ative o ambiente:
   `source .venv/bin/activate`
4. Instale as dependências:
   `pip install -r requirements.txt`
5. Copie o exemplo de variável de ambiente:
   `cp .env.example .env`
6. Preencha o arquivo `.env` com os valores do provedor e da chave:
   `LLM_BASE_URL=https://api.openai.com/v1`
   `OPENAI_API_KEY=seu_token_aqui`
   `MODEL_NAME=gpt-4.1-mini`
7. Execute o demonstrador:
   `PYTHONPATH=. python src/agent.py`

## Como usar
O sistema aceita uma entrada em chat em linguagem natural, como:
`Curti muito Severance. Me indica algo parecido.`

Ele analisa:
- o que a pessoa realmente gostou (clima, mistério, mal-estar, leveza);
- quais títulos estão disponíveis na assinatura do usuário;
- se o título já foi sugerido antes;
- se a recomendação respeita o perfil ou a sessão.

A saída esperada é um JSON com status, título, motivo, plataforma, confiança e próximo passo. O agente também grava a decisão em log local.

## Exemplo real de execução
Este é um exemplo real extraído do log gerado pela execução do script:

```json
{
  "case_id": "simple_success",
  "query": "Curti muito Severance. Me indica algo parecido.",
  "status": "recommendation",
  "decision": {
    "status": "recommendation",
    "title": "Dark",
    "reason": "O clima de mal-estar constante e o mistério perseguem a sensação de estranheza que o usuário descreveu, mais do que o gênero em si.",
    "platform": "Netflix",
    "confidence": "medium",
    "missing_info": "Nenhuma informação pendente na base simulada com dados do caso.",
    "next_step": "Aguardar confirmação do usuário antes de registrar a ação final."
  }
}
```

## O que o sistema não faz
- não sugere títulos fora da assinatura;
- não repete recomendação já recusada;
- não inventa um item sem evidência; quando não encontra candidato, responde `no_match`.

## Documentos principais
- [docs/case.md](docs/case.md)
- [docs/modelos.md](docs/modelos.md)
- [docs/fontes.md](docs/fontes.md)
- [docs/autopsia.md](docs/autopsia.md)
- [logs/demo_runs.json](logs/demo_runs.json)
