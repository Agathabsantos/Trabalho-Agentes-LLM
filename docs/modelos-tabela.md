<!-- Gerado por src/benchmark_modelos.py em 2026-09-19 18:11 -->
<!-- Nao editar a mao: cole no docs/modelos.md secao 4 -->

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
