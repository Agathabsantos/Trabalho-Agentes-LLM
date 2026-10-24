# Human-in-the-loop

## Ponto de parada e perfil

Toda recomendação proposta interrompe o grafo **antes** de gravar no histórico.
O histórico afeta recomendações futuras, portanto a decisão é mostrada ao
**responsável pela conta** (não ao modelo e não necessariamente ao perfil que
está assistindo). A decisão não é sobre elegibilidade — assinatura,
classificação, histórico e fonte continuam sendo validados pelo código.

A pausa mostra:

- ação exata: gravar “título” como recomendado no histórico de `user_id`;
- plataforma listada na assinatura;
- justificativa e trecho-fonte que sustentam a sugestão;
- consequência: o título será excluído de recomendações futuras;
- opção independente de consentir em guardar o clima como memória semântica.

Respostas aceitas via `Command(resume=...)`: `{"decision":"approve"}` ou
`{"decision":"reject"}`. Aprovação editável também aceita `title`, `platform`,
`reason` e `remember_preference`; depois da edição, o código confirma que o
novo título veio dos candidatos/evidências e respeita assinatura/classificação.
Uma edição inválida vira rejeição sem escrita.

## Checkpoint, expiração e silêncio

O nó usa `interrupt()` e a retomada usa `Command(resume=...)` no mesmo
`thread_id=session_id`. O grafo reexecuta o início do nó `approval`; não existe
efeito colateral antes do interrupt. O checkpointer é `SqliteSaver`, em
`dados/checkpoints.sqlite`.

Prazo declarado: **24 horas** a partir da proposta. `expirar_pendencia(thread_id)`
é a rotina de scheduler: após o prazo, retoma com rejeição e encerra sem gravar.
Também, se uma resposta humana tentar retomar tardiamente, o nó força rejeição.
A varredura é `python src/expirar_pendencias.py`: percorre todas as threads do
checkpointer (`varrer_pendencias`), rejeita só as vencidas e imprime em JSON os
`thread_id` expirados. Ela é feita para rodar de hora em hora por cron ou
systemd timer; o exemplo de crontab está no cabeçalho do script. Com execução
horária, uma pendência fica aberta no máximo 25 horas. Uma thread que falha (checkpoint corrompido ou
ilegível) é registrada em `threads_com_falha` e a varredura segue para as outras;
o script termina com código 1 para o cron alertar. O teste
`test_sweep_survives_a_corrupted_thread` insere um checkpoint inválido antes da
thread vencida e confere que ela expira mesmo assim. O teste
`test_scheduler_sweep_expires_only_overdue_threads` cria três threads (uma
vencida, uma dentro do prazo, uma já encerrada) e confere que só a vencida é
rejeitada, sem escrita no histórico, e que uma segunda varredura não faz nada.
O agendamento em si (a linha no crontab) é da máquina que hospeda o sistema e
não está no repositório; sem ele, a pendência continua parada no checkpoint e
nunca segue em silêncio. Alertar o responsável antes do prazo continua fora do
protótipo.

## Idempotência da aprovação

A chave é SHA-256 de JSON canônico com `{user_id,title,platform,mood,reason,
remember_preference}`. Mesmo conteúdo produz a mesma chave. O SQLite executa
`BEGIN IMMEDIATE`, procura `acoes_idempotentes` e grava histórico, episódio e
chave numa única transação. Retorno:

- primeira chamada: `gravado=true`, `ja_existia=false`;
- repetição: `gravado=false`, `ja_existia=true`, mesmo ID; nenhuma nova linha.

`tests/test_graph.py::test_duplicate_approval_write_is_idempotent` envia duas
vezes a mesma resposta à função `resumir`; a segunda retomada repete a operação
idempotente e devolve `ja_existia=true`. `logs/part2_runs.json` contém os dois
resultados de escrita da demonstração. Se a pessoa altera motivo ou marca
memória semântica na segunda chamada, o conteúdo e a chave mudam; isso é uma
nova ação, e o cliente deve usar o mesmo payload para retry idempotente.

## Estado da evidência

Os testes automáticos exercitam pausa, retomada, rejeição/edição, rotina de
expiração e idempotência.
O log de demonstração usa aprovador simulado, não uma pessoa real. Não existe
interface de produção nem identidade autenticada de responsável; os testes
provam o protocolo de checkpoint, não governança operacional.
