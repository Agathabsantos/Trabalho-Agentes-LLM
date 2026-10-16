# Base de conhecimento — registro histórico do plano v1

> **Substituído pela decisão implementada:** consulte [rag.md](rag.md). Este
> arquivo existia antes da Parte 2 e propunha TMDB e busca vetorial; nenhuma
> dessas integrações foi feita. Mantido apenas para deixar registrada a mudança
> de decisão, sem apresentar o plano antigo como arquitetura atual.

A Parte 2 escolheu fixtures sintéticas versionadas em
`dados/streaming_catalog.json` e `dados/rag_corpus.jsonl`; consulta estruturada
SQLite para registros e busca textual lexical para reviews curtos. Não há fonte
externa consultada nem disponibilidade de catálogo real. As motivações,
perguntas classificadas e o teste de documento revogado estão em `docs/rag.md`.
