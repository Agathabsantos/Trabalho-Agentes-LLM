# Memória e gestão da conversa

## Dois níveis e três estruturas

| Nível | Conteúdo neste case | Persistência | Escopo |
|---|---|---|---|
| Curto prazo | texto da conversa, identidade de sessão, filtros recebidos, candidatos, fontes, proposta pendente, resposta humana, trajetória | checkpointer LangGraph SQLite em `dados/checkpoints.sqlite` | execução/thread retomável |
| Longo prazo | eventos de recomendação aprovados; preferência semântica somente se opt-in; regra operacional | tabelas SQLite (`episodios`, `historico`, `memoria_semantica`) e prompts no pacote | entre threads/execuções |

**Identificação:** `thread_id=session_id`; o app fornece `user_id` separado. Mesma
sessão retoma checkpoint; duas sessões simultâneas do mesmo usuário recebem IDs
diferentes e não misturam estado curto. O CLI cria um ID novo por execução.
Não há autenticação real no protótipo: o app de produção precisa derivar o
`user_id` de sessão autenticada, nunca confiar no texto do usuário.

**Checkpointer:** `SqliteSaver` persiste em `dados/checkpoints.sqlite`. É local,
com retenção e permissões de arquivo não gerenciadas pelo projeto; não é banco
compartilhado/alta disponibilidade. O checkpoint da pausa preserva a proposta
pendente. Se o processo morre, o estado permanece no arquivo, mas a aprovação
só continua quando um operador retomar o mesmo `thread_id`.

### O que vai ao checkpoint para retomar sem repetir escrita

`messages`, `user_id`, `session_id`, filtros, `mood`, título de referência,
`candidates`, `evidence`, `pending_action`, `human_response`, chave de
idempotência e `persist_result`. `persist` ocorre só depois do `interrupt`; ao
retomar, o nó `approval` reexecuta desde o início, mas não tem efeito lateral
antes de receber a resposta. Se o mesmo conteúdo chegar novamente à escrita, a
chave impede duplicação.

### Ordem de descarte da janela

Uma mesma thread aceita novas mensagens após a execução terminar e o modelo
recebe apenas o texto atual para interpretar; o histórico integral não é
reenviado em cada prompt. A fonte selecionada é recuperada em seguida. Portanto
a janela de inferência não cresce com as mensagens antigas. O checkpoint, por
outro lado, mantém mensagens e trajetória enquanto o `thread_id` persistir; não
há truncamento/sumarização nem prazo de retenção implementados. Se a aplicação
passar a incluir o histórico na inferência, a ordem decidida será: (1) remover
evidência com menor score já consumida, (2) eventos episódicos antigos que não
alteram filtros, (3) mensagens conversacionais antigas. Nunca descartar texto
atual, restrições da conta, fonte necessária à citação ou proposta pendente.
Até implementar isso, conversas longas podem aumentar o arquivo de checkpoint;
não há descarte automático silencioso.

### Checkpoint x memória x RAG

| | Checkpoint | Memória | RAG |
|---|---|---|---|
| Escopo | thread atual | usuários/execuções | corpus curado externo à execução |
| Propósito | retomar a pausa e o estado | lembrar decisões anteriores/opt-in | consultar evidência de catálogo |
| Forma | estado íntegro | episódio FTS ou chave-valor | review versionado com fonte |
| Leitura | ao carregar thread | até 3 eventos relacionados por busca lexical e perfil por chave | na etapa `retrieve`, uma busca textual |
| Escrita | framework/checkpointer | código + aprovação/opt-in | curador altera arquivos do corpus |

Recuperação por relevância oferece uma pequena seleção de episódios do mesmo
usuário sem colocar o estado completo de todas as conversas no prompt. Ela deixa
para trás eventos irrelevantes ou lexicalmente não relacionados; a busca é
limitada e não constitui memória integral nem similaridade vetorial.

## As três memórias no case

| Tipo | Estrutura | Conteúdo/política |
|---|---|---|
| Episódica | tabela `episodios` + FTS5 | uma linha por recomendação aprovada; guarda clima e justificativa, junto ao histórico. `buscar_episodios` limita a 3 resultados por usuário. O evento prova recomendação, não aceitação/gosto. |
| Semântica | `memoria_semantica` chave-valor por `user_id` | somente se responsável escolhe `remember_preference=true`; não inferir gosto de uma recomendação. Uma chave por usuário, carimbo `atualizado_em`. |
| Procedural | `src/prompts/interpret_request.txt` e regras Python | política de interpretação, precedência do pedido, filtros, recusa e autorização; revisada por mantenedores. |

O código é o escritor: uma linha episódica por recomendação aprovada; uma linha
semântica somente após opt-in explícito.

**Volume por execução.** Cada caso de `logs/part2_runs.json` registra em
`memory_written` as linhas e os bytes de texto gravados por tabela. Uma
execução aprovada grava 1 linha em `historico`, 1 em `episodios` (mais o FTS) e,
só com opt-in, 1 em `memoria_semantica`. Uma execução que pergunta, recusa ou é
rejeitada grava zero. Os bytes medidos estão na tabela abaixo.

| Tabela | Linhas por execução aprovada | Bytes por linha (medido no log) |
|---|---|---|
| `historico` | 1 | *a preencher após `python src/demo_part2.py`* |
| `episodios` | 1 | *a preencher* |
| `memoria_semantica` | 0 ou 1 (opt-in) | *a preencher* | O ato de aprovar a escrita no histórico não autoriza automaticamente
perfilamento semântico.

## Como a memória muda ou desaparece

| Causa | Escolha | Efeito implementado/limite |
|---|---|---|
| Contradição | parcialmente aplicável à preferência opt-in | `atualizar_preferencia` faz upsert por chave e substitui o valor anterior; `atualizado_em` registra a revisão mais recente. Não há ingestão de fatos retroativos. |
| Decaimento | não implementado | recomendação prévia permanece no histórico para cumprir “não repetir”; dados sintéticos são poucos. Em produção, crescimento monotônico exige retenção/custo medidos. |
| Remoção | implementada: `python src/remover_titular.py <user_id>` | Razão: privacidade. O sistema guarda, por `user_id`, o que foi recomendado e, com opt-in, o clima preferido. Apaga numa transação e depois varre de novo (ver abaixo). |

### Remoção a pedido do titular: cobertura

| Estrutura onde o `user_id` é gravado | O que a remoção faz | Como a varredura confere |
|---|---|---|
| `historico` | apaga as linhas do titular | `COUNT(*)` por `user_id` |
| `episodios` e `episodios_fts` | apaga as linhas e o índice FTS5 | `COUNT(*)` nas duas tabelas |
| `memoria_semantica` | apaga a preferência opt-in | `COUNT(*)` por `user_id` |
| `acoes_idempotentes` | apaga as chaves das escritas do titular (a chave não tem `user_id`; sobra apareceria como chave órfã) | chaves sem histórico correspondente |
| checkpoint (`dados/checkpoints.sqlite`) | `delete_thread` em toda thread cujo estado tem esse `user_id`; isso inclui argumentos de cada passo e pendências | busca dos bytes do `user_id` nas colunas `checkpoint`, `metadata` e `value` |
| `logs/*.json` | **não apaga**: são arquivos versionados no git | o script lista em quais logs o id aparece; reescrever o histórico do repositório é decisão de quem mantém o projeto |
| `dados/historico_seed.jsonl` | **não apaga**: é fixture e reconstrói o banco | um titular real nunca deveria estar no seed |
| memória procedural (prompts e regras) | nada a apagar | nenhuma regra cita titular; confere-se com `grep` |

O teste `test_holder_removal_clears_every_structure_and_restores_behavior` segue
o roteiro do enunciado: grava (aprova The Office com opt-in), verifica que o
comportamento mudou (o título não volta a ser proposto), remove, varre as
estruturas (todas com zero) e verifica que o comportamento voltou (The Office é
proposto de novo). Um segundo usuário gravado antes continua intacto.

O índice não precisa ser reconstruído: a remoção é um `DELETE` pontual, então
também serve à recuperação de incidente, não só à privacidade.

O case usa apenas IDs sintéticos, e não há dado sensível pessoal necessário à
recomendação.

**O que não entra:** gabarito de avaliação, segredo/API key, histórico completo
no contexto do modelo, disponibilidade externa não verificada e preferência
inferida sem opt-in. O corpus RAG não é memória do usuário e só o curador o
edita.

## O que passa de conversa para longo prazo

Somente recomendação aprovada no histórico/episódico. A recusa da pessoa e o
play não são observados pelo app atual; nenhuma inferência automática de “gostou”
é válida. A preferência semântica só sobrevive se a pessoa responsável aceitar
a opção de gravação. Mensagens, candidatos temporários e fontes da conversa
continuam no checkpoint e não viram perfil por padrão.
