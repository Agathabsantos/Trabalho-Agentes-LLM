# Agente de recomendação de próximo título — Parte 1

## Integrantes
- Agatha Barbosa Marinho dos Santos
- Bruna Kinjo Luiz Pinto
- Kayke Ahrens Biscegli
- Matheus da Silva Marini

## O problema, em uma frase

Um agente que identifica o motivo real do gosto do usuário em um título e recomenda a próxima série ou filme disponível na conta, sem repetir itens e sem sair do perfil ou da assinatura.

---

## Como rodar

Do zero, em menos de 5 minutos:

```bash
git clone <url-do-repositorio>
cd Trabalho-Agentes-LLM

python3 -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt

cp .env.example .env               # e preencha o .env (veja abaixo)

python src/agent.py                # roda os 5 casos
python src/verificador.py          # confere o resultado contra o gabarito
```

O `.env` precisa de três variáveis. **Nenhuma delas vai para o git** — o `.env` está no `.gitignore`.

| Variável | O que é | Exemplo |
|---|---|---|
| `OPENAI_API_KEY` | chave do provedor do **modelo** (não é chave do TMDB) | `sk-...` |
| `LLM_BASE_URL` | endpoint do provedor. Vazio = padrão da OpenAI | `https://api.mistral.ai/v1` |
| `MODEL_NAME` | id do modelo, como o provedor o chama | `ministral-8b-2512` |

Trocar de provedor (OpenAI, Mistral, modelo local compatível) muda **só essas duas variáveis**, nenhuma linha de código.

**Não tem chave agora?** `python src/agent.py --sem-modelo` roda o mesmo laço com uma política de regras fixas, sem chamar o LLM. Serve para ver o sistema funcionar — **mas não vale como entrega**, e todo log gerado assim sai carimbado com `"motor": "heuristica_sem_modelo"`.

---

## Como usar

### O que a pessoa digita

Uma frase em linguagem natural dizendo o que ela gostou e o que quer agora:

```
Curti muito Severance. Me indica algo parecido.
Quero algo leve e sem ficar pensando demais.
```

Nesta entrega as frases vêm dos 5 casos de `dados/cases.json`, junto com o contexto da conta (quais plataformas o usuário assina, qual a classificação do perfil, o `user_id`). Esse contexto é **injetado pelo código**, não perguntado — o sistema não pergunta o que já sabe.

### O que o sistema faz com isso

Consulta o título citado no catálogo (SQLite), decide **qual clima o usuário realmente quer** — que nem sempre é o do título que ele citou —, busca candidatos já filtrados por assinatura, classificação e histórico, escolhe um, e grava a decisão. Se nada passa nos filtros, ele para e diz por quê, em vez de sugerir algo que a pessoa não consegue assistir.

### Que saída ela recebe

Um objeto JSON com sete campos:

| Campo | Como interpretar |
|---|---|
| `status` | `recommendation` = achou; `no_match` = não há título válido, e o `reason` diz por quê |
| `title` | o título recomendado, ou `null` |
| `reason` | a evidência do catálogo que sustenta a escolha — no máximo 2 frases |
| `platform` | em qual plataforma **assinada** o título está |
| `confidence` | `low`, `medium` ou `high` |
| `missing_info` | o que o sistema ainda não sabe |
| `next_step` | qual é a próxima ação do processo |

### Um exemplo completo, de uma execução real

> Saída copiada de `logs/demo_runs.json`, de uma execução com o modelo
> (`"motor": "modelo"`, `"modelo": "ministral-8b-2512"`). Para reproduzir:
> configure o `.env` e rode `python src/agent.py`.

**Entrada** (caso `caso_simples`): usuário `u-001`, assina Netflix, perfil 16+, cita *Severance* como referência, descreve o clima como "mal-estar constante".

```
$ python src/agent.py

  caso_simples      -> Dark   (4 passos, 3 ferramentas, parada: resposta_final)
```

**Trajetória registrada:**

```
passo 1 | consultar_titulo        | sem erro
passo 2 | buscar_candidatos       | sem erro  -> candidatos: ["Dark"]
passo 3 | registrar_recomendacao  | sem erro
passo 4 | resposta final          | parada: resposta_final
```

**Saída:**

```json
{
  "status": "recommendation",
  "title": "Dark",
  "reason": "O clima de mal-estar constante e misterio é semelhante ao de Severance, com uma narrativa que gera inquietação contínua, como destacado nas avaliações: 'o clima de inquietacao e o que chama atencao' e 'sentimento de que algo esta errado o tempo todo'.",
  "platform": "Netflix",
  "confidence": "high",
  "missing_info": "nenhuma",
  "next_step": "nenhuma"
}
```

**Conferindo o resultado:**

```
$ python src/verificador.py

CASO                              ESPERADO        OBTIDO          ACERTO   INVARIANTES
--------------------------------------------------------------------------------------------
caso_simples                      Dark            Dark            OK       ok
divergencia_usuario_vs_sistema    The Office      The Office      OK       ok
registro_inexistente              no_match        no_match        OK       ok
nao_dispara_acao                  no_match        no_match        OK       ok
nao_repete_recomendacao           The OA          The OA          OK       ok
--------------------------------------------------------------------------------------------
ACERTOS:     5/5   (minimo exigido: 4/5)
INVARIANTES: 0 violacoes   (maximo tolerado: 0)

RESULTADO: APROVADO
```

### O que o sistema **não** faz

- **não sugere fora da assinatura.** Se o título só existe numa plataforma que o usuário não assina, ele não aparece — e se o modelo insistir, a ferramenta de escrita recusa e explica por quê;
- **não repete.** Título já oferecido àquele usuário é excluído da busca;
- **não passa da classificação** do perfil da sessão;
- **não inventa título.** Se a referência não existe no catálogo, ele responde `no_match` e pede o nome correto, em vez de chutar algo parecido;
- **não tem interface de chat.** Nesta entrega o agente é um programa de linha de comando: lê os pedidos de `dados/cases.json` e escreve JSON. O chat é o canal previsto no `docs/case.md`, e a interface é escopo da Parte 2;
- **não conversa em várias trocas.** É uma troca só; o refinamento é escopo da Parte 2;
- **não dá play.** Ele diz *qual* título e *em qual* plataforma assinada; ir até lá é com a pessoa. Não é um recurso dentro da Netflix ou do Prime;
- **não usa catálogo real.** Os dados são simulados — ver `docs/fontes.md`.

**Quando ele não sabe responder**, a saída vem com `status: "no_match"`, e o `reason` diz qual filtro barrou (assinatura, classificação ou histórico vazio de candidatos). Ele nunca devolve uma sugestão sem evidência.

---

## Como verificar que o sistema faz o que diz

```bash
python src/verificador.py              # 5 casos x gabarito + 4 invariantes
python src/verificador.py --autoteste  # prova que o verificador não é vazio
```

O `--autoteste` injeta quatro decisões **propositalmente erradas** — uma fora da assinatura, uma acima da classificação, uma repetida e um título inventado — e falha se alguma passar batido. Um verificador que aprova tudo dá falsa segurança.

O gabarito (`expected_title`, `expected_status`) **não é visível ao agente**: só o `verificador.py` lê esses campos.

---

## Estrutura

```
README.md              este arquivo
requirements.txt       dependências com versão fixada
.env.example           nomes das variáveis, sem nenhum valor

docs/
  estado-da-entrega.md o que foi feito, o que falta, como conferir
  case.md              o problema, usuários, workflow, negócio, verificador
  modelos.md           os 3 candidatos, a conta de custo, a decisão
  arquitetura.md       §0 = o que está implementado; §1+ = alvo da Parte 2
  fontes.md            tudo que foi consultado, com link
  autopsia.md          a autópsia do caso real
  base-de-conhecimento-v1.md  as fontes que o RAG da Parte 2 vai indexar

prompts/
  system.txt           v2 — carimbado com modelo, parâmetros e técnica
  user_prompt.txt      v2 — template do contexto da conta

src/
  agent.py             o laço: estado, orçamento, terminação, trajetória
  motores.py           MotorModelo (LLM) e MotorHeuristico (sem LLM)
  ferramentas.py       as 4 ferramentas; erro volta como dado
  catalogo_db.py       camada de acesso SQLite (item 4.2; vira MCP na Parte 2)
  verificador.py       confere gabarito + invariantes; tem autoteste
  benchmark_modelos.py roda os 5 casos nos 3 candidatos (item 3.3)

dados/
  streaming_catalog.json  catálogo simulado, 9 títulos
  historico_seed.jsonl    histórico inicial
  cases.json              os 5 casos, com gabarito e descrição do que testam
  catalogo.db             SQLite derivado (não versionado)

logs/
  demo_runs.json          as execuções demonstradas
```

---

## O que ainda falta (declarado, não escondido)

| Pendência | Onde | Quem resolve |
|---|---|---|
| Rodar com chave e regerar `logs/demo_runs.json` com `"motor": "modelo"` | `src/agent.py` | o grupo |
| Rodar o benchmark dos 3 modelos e preencher `modelos.md` §4 | `src/benchmark_modelos.py` | o grupo |
| Medir a linha de base: 10 decisões cronometradas | `docs/case.md` §5.2 | o grupo |
| Preencher a tabela de preço por token na data da entrega | `docs/modelos.md` §3 | o grupo |
