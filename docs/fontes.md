# Fontes consultadas

## Documentação técnica

| Fonte | Link | Para que serviu |
|---|---|---|
| OpenAI — API Reference (Chat Completions) | https://platform.openai.com/docs/api-reference/chat | formato de `chat.completions.create`, que substituiu a `responses.create` usada na v1 do código |
| OpenAI — Function calling | https://platform.openai.com/docs/guides/function-calling | esquema das 4 ferramentas em `src/ferramentas.py:ESQUEMA_FERRAMENTAS` |
| OpenAI — Structured outputs | https://platform.openai.com/docs/guides/structured-outputs | contrato de saída JSON em `prompts/system.txt` |
| OpenAI — Pricing | https://openai.com/api/pricing/ | **não consultada**: os candidatos OpenAI saíram da lista em 18/09/2026 (ver `modelos.md` §2), então o preço deles não entra na conta |
| Mistral AI — Documentação | https://docs.mistral.ai/ | confirmar a compatibilidade OpenAI do endpoint, que é o que permite trocar de provedor mudando só `LLM_BASE_URL` |
| Mistral AI — API Pricing | https://mistral.ai/pricing/api | **consultada em 18/09/2026**: preencheu a tabela de preço de `modelos.md` §3 (Ministral 3B/8B/14B) |
| Mistral AI — Pricing (docs) | https://docs.mistral.ai/inference/pricing | **consultada em 18/09/2026**: segunda fonte, usada para conferir os preços acima. As duas batem |
| SQLite — Documentação | https://www.sqlite.org/docs.html | modelagem das tabelas `titulos` e `historico` em `src/catalogo_db.py` |
| Python — `sqlite3` | https://docs.python.org/3/library/sqlite3.html | camada de acesso e `row_factory` |
| Python — `unicodedata` | https://docs.python.org/3/library/unicodedata.html | normalização de acentos no casamento de clima (`catalogo_db.normalizar`) |
| Model Context Protocol | https://modelcontextprotocol.io/ | conferir que `catalogo_db.py` tem formato reescrevível como servidor MCP na Parte 2 |

## Material da disciplina

- Enunciado da Parte 1 (`01-entrega-parte-1`) — requisitos, rubrica de avaliação e os quatro casos difíceis exigidos no item 4.5.
- Visão geral do trabalho (`00-visao-geral`) — os quatro antipadrões, usados para checar o tema.
- Nota 01 da aula de casos de uso — tabela de eixos de ganho, usada na `case.md` §5.2.
- Aula 03, versionamento de prompt — origem do carimbo `prompt × modelo × parâmetros` no cabeçalho de `prompts/system.txt`.
- Caso Klarna, visto em aula — origem da tensão negócio × usuário declarada na `case.md` §5.2.

## Dados

Os dados de catálogo e histórico em `dados/` são **simulados e produzidos pelo grupo**. Os títulos citados (Severance, Dark, The Office e outros) são obras reais, mas **as tags de clima, as plataformas, as classificações e as avaliações no arquivo foram escritas por nós** para o exercício — não foram extraídas de nenhuma base e não correspondem à disponibilidade real em nenhuma plataforma.

Isso é deliberado, e o `case.md` §8 explica como a dificuldade foi preservada. Nenhuma API externa de catálogo (TMDB, IMDb, JustWatch) é consultada nesta entrega; a integração com catálogo real é escopo da Parte 2.

## Observação sobre o que NÃO foi consultado

Não usamos leaderboard público para escolher o modelo. O enunciado pede explicitamente que a escolha venha de verificação própria no domínio do caso, e é isso que `src/benchmark_modelos.py` produz — ver `modelos.md` §4.
