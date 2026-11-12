# Histórico de mudanças

O que mudou no sistema, por versão, com o commit. A versão fica em
`src/versao.py` e vai para todo trace (`app.versao_sistema`); a suíte se recusa
a rodar com `--versao` diferente do código.

## Devolutiva da Parte 1 (nota 9,9), aplicada em 2026-11-12

A devolutiva da Parte 2 ainda não chegou. Da Parte 1, o que ainda valia para o
código atual:

| Apontado | O que mudou |
|---|---|
| Rigor do prompt (parcial): técnica, contrato e o que a etapa impede estavam só no cabeçalho do prompt, não em comentário no código | comentário na única chamada ao modelo do grafo, `src/graph.py` (nó `triage`) |
| `Ferramentas` recebia o caso inteiro, com `expected_title` | `src/agent.py` passa o caso sem as chaves `expected_*` |
| `funcao(**args)` não tratava `TypeError` de argumento inesperado | `src/agent.py` devolve `argumentos_invalidos` como dado ao modelo |
| `dados/history.jsonl` não era lido por nenhum módulo | removido |
| Documentos desatualizados (README, cabeçalho do `case.md`) | já corrigido na Parte 2: o README foi reescrito e o `case.md` ganhou o escopo das versões |

Não mudam o que a suíte mede (o agente da Parte 1 não é o sistema avaliado),
por isso a versão continua 1.1.0.

## Depois da rodada 1.1.0: correções de registro (sem mudança de versão)

Não mudam o que a suíte mede, por isso a versão continua 1.1.0.

- **C4 passa a aparecer no trace:** a retomada (`graph.resumir`) limpava o motivo
  antes de entregá-lo ao grafo, e o nó `approval` não via o que registrar; na
  rodada 1.1.0 o motivo saiu limpo, mas `app.controles` ficou vazio. Agora a
  retomada só usa o texto limpo para comparar reenvios, e o nó limpa e registra.
  Teste: `test_limpeza_fica_registrada_no_estado_e_no_trace`.
- **`arvore_suja`:** a suíte ignora arquivos não rastreados ao checar a árvore,
  porque a própria pasta da rodada marcava toda rodada como suja.

## 1.1.0 (Parte 3, etapa 2): controles fora do prompt

Commit: `632558f`. Rodada: `evals/resultados/1.1.0-modelo-20261112T025748Z`.

- **C1, allowlist do endpoint (ASI04):** `src/seguranca.py`, aplicado no
  `triage` antes de criar o cliente. Endpoint fora da lista termina em `error`
  sem chamada.
- **C3, quarentena de evidência (ASI06, ASI09):** trecho com linguagem de
  instrução ou com mais de 160 caracteres não volta da busca (`src/rag.py`).
- **C4, memória sem dado pessoal (Parte 3, seção 3.4):** o motivo editado pelo
  aprovador perde telefone, e-mail, CPF e chaves antes do estado, do trace e da
  escrita (`src/graph.py`, nó `approval`).
- **Testes:** `tests/test_controles.py`, 9 testes (C1, C2, C3 e C4); o décimo, do registro do C4, entrou depois da rodada.
- **Efeito medido:** segurança de 33,3% para 66,7% e média de 75,9% para 79,3%
  na suíte com o modelo; `rec-27` e `rec-28` passaram a passar e `rec-26`
  (injeção, risco aceito) oscilou no sentido contrário (`docs/evals.md`, seção 4).

## 1.0.0 (Parte 3, etapa 1): o sistema da Parte 2, instrumentado

Commits: `3cabd61` (telemetria e suíte) e `e2105a1` (espera no 429). Rodada:
`evals/resultados/1.0.0-modelo-20261112T021803Z`, commit `338ee43`.

- **Telemetria OpenTelemetry** (`src/telemetria.py`): spans `invoke_agent`,
  `chat` e `execute_tool` nas convenções GenAI, com motivo de término e versão
  na raiz; exportação em JSONL; leitor `src/ver_trace.py`.
- **Ponto de entrada único** `graph.invocar`, usado pelo CLI, pela demo e pela
  suíte; retomada e expiração também abrem span raiz.
- **Suíte de avaliação** (`evals/`): golden dataset de 29 casos, verificações
  determinísticas, de trajetória e de resultado, juiz com rubrica, comparação
  entre rodadas e métricas.
- **RAG:** o corpus pode ser trocado por `RAG_CORPUS`, para a suíte injetar um
  trecho envenenado sem mexer em `dados/`.
- O comportamento do agente não mudou: os 24 testes da Parte 2 passam sem
  alteração de asserção.
- **Retry em 429:** a primeira rodada com o modelo (2026-11-11, descartada)
  teve 25 de 27 chamadas recusadas com `RateLimitError` pela camada grátis da
  Mistral, e cada uma terminou em `error`. A chamada ao modelo passou a esperar
  2, 4 e 8 s e tentar de novo só nesse erro, dentro do teto de 20 s
  (`ESPERAS_429` em `src/graph.py`); cada espera vira o evento `rate_limit_429`
  no span `chat`. Teste: `tests/test_retry.py`.

## Antes da Parte 3

| Commit | O que mudou |
|---|---|
| `e3dd06b` | README atualizado com o estado da Parte 2 e dos exercícios |
| `2fd5f5a` | Exercício 14: mitigações de ASI02 (ferramentas presas ao usuário da sessão), ASI03 (classificação ausente vale `L`, `thread_id` aleatório) e ASI08 (varredura isolada por thread) |
| `6c3ebf4` | Parte 2: prompt v2 few-shot, remoção por titular, expiração de pendências, teste A/B |
| `9aa111e` | Parte 2: grafo LangGraph, RAG, memória e pausa humana |
| `33c83e7` | Parte 1: agente com o modelo, benchmark dos candidatos e linha de base medida |
