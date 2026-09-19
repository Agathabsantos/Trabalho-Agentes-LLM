# Estado da entrega — Parte 1

> Documento de passagem de contexto, escrito em 19/09/2026.
> Serve para qualquer pessoa retomar o trabalho
> sabendo o que foi feito, por quê, e o que ainda falta.

---

## 1. Onde o trabalho está

| Item da rubrica | Estado |
|---|---|
| Qualidade da escolha do tema | ✅ pronto |
| Usuários e interação | ✅ pronto |
| Workflow (8 passos, quem decide, escritas marcadas) | ✅ pronto |
| Justificativa de negócio | ✅ linha de base **medida** em 19/09/2026: 11,7 min, 10 cronometragens |
| Honestidade da análise de modelos | ✅ benchmark rodado em 18/09/2026, 3 candidatos, preços consultados |
| O agente rodando | ✅ 5/5 com `ministral-8b-2512` em 18/09/2026 |
| Entrega como projeto | ✅ pronto |
| Justificativa da arquitetura | ✅ pronto |
| Rigor do prompt | ✅ pronto |

**Resumo:** o agente roda com modelo real e passa **5/5 com 0 violações**. O
benchmark dos 3 candidatos (duas rodadas), os preços por token e a linha de
base medida estão feitos. O defeito no laço de tool calling foi corrigido em
19/09/2026. **Todos os itens da rubrica estão atendidos.** Sobra dividir os
commits entre os integrantes.

---

## 2. O que foi corrigido, e por quê

A versão anterior (commit `18779ee`) tinha problemas que iam além de bug: eram
afirmações que o repositório não sustentava. A auditoria encontrou o seguinte.

### 2.1 Problemas de honestidade

| Problema | Evidência | Correção |
|---|---|---|
| **O modelo nunca era chamado.** `fallback_model_response()` devolvia títulos escritos à mão, e um `except Exception: pass` escondia a ausência da biblioteca e da chave | Rodava sem `openai` instalado e sem `.env`, produzindo log idêntico ao commitado | Sem chave, o programa para com exit 2 e mensagem clara. O modo `--sem-modelo` existe, mas carimba todo log com `"motor": "heuristica_sem_modelo"` |
| **O código lia o gabarito.** `if case["id"] == "divergence..."` e `if case.get("expected_status") == "no_match"` | `agent.py:111` e `agent.py:213` da v1 | Removidos. Gabarito só é lido por `verificador.py` |
| **O exemplo do README era inventado.** Dizia "extraído do log", mas o log tinha outro título | README dizia `Dark`; log dizia `The OA` | Exemplo copiado do log, com a proveniência declarada |
| **A tabela de benchmark nunca rodou.** 5 casos × 3 modelos com veredictos escritos à mão | Nenhum log, nenhum script, nenhuma chamada de modelo no projeto | Tabela removida. `src/benchmark_modelos.py` a gera a partir de execução real |
| **A linha de base dizia "medida"** sem as 10 medições | `case.md` §5.2 da v1 | Rebaixada para estimativa declarada, com o protocolo de medição e a tabela a preencher |

### 2.2 Problemas de correção

| Problema | Correção |
|---|---|
| Não havia verificador em código; o critério prometia 3/4 e o resultado real era 2/4 | `src/verificador.py`, com gabarito + 4 invariantes + `--autoteste` |
| `caso_simples` pedia Dark (16+) para perfil 14+ — gabarito impossível | Perfil de `u-001` ajustado para 16+ |
| `no_action` mandava recomendar Servant, violando assinatura **e** classificação | Virou `nao_dispara_acao`, esperando `no_match` — que é o que o item 4.5 do enunciado pede desse caso |
| `history.jsonl` era escrito mas nunca lido; a regra "não repetir" era decorativa | Histórico no SQLite, lido por `buscar_candidatos` e revalidado na escrita. Caso `nao_repete_recomendacao` adicionado para testar |

### 2.3 Requisitos formais que faltavam

| Requisito | Antes | Agora |
|---|---|---|
| 4.2 — integração com software tradicional | `json.load()` dentro do `agent.py` | SQLite + camada de acesso exclusiva (`catalogo_db.py`) |
| 4.1 — laço com estado explícito | pipeline fixo de 4 passos | laço real com `EstadoAgente` |
| 4.1 — orçamento | variável morta, só copiada para o log | comparada a cada volta do laço |
| 4.1 — terminação registrada | parcial | `motivo_da_parada` com 5 valores possíveis |
| 4.1 — erro de ferramenta como dado | inexistente | `{"erro", "detalhe", "como_corrigir"}` em toda ferramenta |
| 4.1 — prompts carimbados | sem cabeçalho | versão, modelo, parâmetros, técnica e por quê |
| API | `responses.create` (só OpenAI) | `chat.completions.create` com tool calling |
| `.env.example` | continha valores | só os nomes |
| `fontes.md` | sem nenhum link | tabela com links |

---

## 3. Resultado atual

Executado em 18/09/2026 com `ministral-8b-2512` (`logs/demo_runs.json`,
carimbado `"motor": "modelo"`):

```
CASO                              ESPERADO      OBTIDO        ACERTO   INVARIANTES
caso_simples                      Dark          Dark          OK       ok
divergencia_usuario_vs_sistema    The Office    The Office    OK       ok
registro_inexistente              no_match      no_match      OK       ok
nao_dispara_acao                  no_match      no_match      OK       ok
nao_repete_recomendacao           The OA        The OA        OK       ok

ACERTOS:     5/5   (minimo exigido: 4/5)
INVARIANTES: 0 violacoes   (maximo tolerado: 0)
RESULTADO: APROVADO
```

**Este é o número da entrega**, não a heurística. 28.341 tokens no total,
3,2 idas ao modelo por execução, US$ 0,000850 por execução — conta em
`docs/modelos.md` §3, que também registra a variação de 8% entre duas
execuções do mesmo modelo.

Benchmark dos 3 candidatos (`docs/modelos.md` §4, segunda rodada, laço
corrigido): 3B **4/5**, 8B **5/5**, 14B **5/5**, zero violações e zero erros HTTP
nos três. O 3B perde só na divergência, e perde de verdade — ver `case.md` §7.

## 4. O que falta

### 4.1 ~~Medir a linha de base~~ — feito em 19/09/2026

10 cronometragens (4 integrantes + 5 amigos), média **11,7 min**, mediana 10.
A estimativa anterior era 14; o ganho caiu de −86% para **−83%** e é o número
que ficou. Tabela e análise em `docs/case.md` §5.2.

### 4.2 ~~Corrigir o laço de tool calling~~ — feito em 19/09/2026

Fila de tool calls em `MotorModelo` (`src/motores.py`). 0 erros HTTP em 12
repetições do 3B e no benchmark completo. Detalhe e o que a correção revelou em
`docs/case.md` §7 e `docs/modelos.md` §4.

### 4.3 Dividir os commits — é do grupo

Todo o trabalho de 18–19/09 está solto na árvore. O enunciado diz que o
histórico "será olhado" como evidência de participação. Se sair como um commit
só, de uma pessoa, o equilíbrio atual (os 4 integrantes já têm commits) some.
Sugestão: um commit por assunto, cada integrante assina um — integração SQLite,
laço do agente, verificador + casos, docs + logs.

## 5. Como conferir que nada regrediu

```bash
grep -rn "expected_" src/agent.py        # tem que voltar VAZIO
python src/agent.py                      # sem chave: exit 2, mensagem clara
python src/verificador.py --autoteste    # prova que o verificador pega erro
python src/verificador.py                # o placar
```

E a conferência que pega a regressão mais perigosa — o exemplo do README
descolar do log:

```bash
python -c "
import json
log=[x for x in json.load(open('logs/demo_runs.json')) if x['case_id']=='caso_simples'][0]['decision']
readme=open('README.md').read()
print('OK' if log['title'] in readme else 'DIVERGIU: README nao bate com o log')"
```

---

## 6. O que vem depois (Partes 2 e 3)

Declarado em `docs/case.md` §10, resumido aqui:

- **RAG (Parte 2):** as avaliações de espectadores, hoje passadas inteiras ao
  modelo. É o que mantém o tema de pé fora do conjunto de teste — ver o risco
  na §11 do `case.md`
- **MCP (Parte 2):** `src/catalogo_db.py` vira servidor MCP. O esquema das
  ferramentas já está declarado em `ferramentas.py:ESQUEMA_FERRAMENTAS`
- **LangChain (Parte 2):** a orquestração do laço de `agent.py`
- **Multiagente (Parte 3):** um curador e um auditor, o segundo verificando se
  a evidência citada sustenta a recomendação
