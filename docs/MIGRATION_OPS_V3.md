# Migração para predictor-ops 3.0 e predictor-core 2.2

Data: 2026-08-09. Branch: `migration/ops-v3`. Base científica: commit
`9f6014b`.

## Mudanças de contrato

- `predictor-ops==3.0.0` controla somente `RunStatus` operacional.
- `scientific_state` é transportado opaquamente no job, heartbeat e event log.
- `predictor-core==2.2.0` fornece o `ScientificState` oficial.
- `COLLECTION_ONLY` não é mais resultado de processo; o job termina como
  `SUCCEEDED` e carrega `scientific_state=COLLECTION_ONLY` separadamente.
- `CLOSED_BY_HUMAN_DECISION` foi removido do enum local e vem do core.
- `NO_UPSTREAM_EVENTS` é outcome do domínio sobre um run operacionalmente
  bem-sucedido.

## Segurança operacional

- `cs-settle` sempre falha fechado com exit code 2.
- `cs-predict` e `cs-ingest-hltv` exigem `--laboratory` ou
  `CS_LABORATORY=1`.
- `cs-collect` e `cs-scheduler` permanecem as superfícies autorizadas de
  coleta arquivística.
- O timer systemd apenas invoca `cs-scheduler`; não interpreta o heartbeat e
  não precisou ser alterado.

## Transparência científica

Os replays somente leitura foram executados antes e depois da troca de
infraestrutura sobre o mesmo banco completo de 17.999 séries. Os resultados
foram idênticos:

| Medida | Antes | Depois |
|---|---:|---:|
| Séries medidas | 11.348 | 11.348 |
| Brier H1 | 0,4551 | 0,4551 |
| Acurácia H1 | 62,2% | 62,2% |
| DM H1 | -13,47; p≈0 | -13,47; p≈0 |
| Brier H2 | 0,4536 | 0,4536 |
| DM H2 | -3,63; p=0,00028 | -3,63; p=0,00028 |

Nenhum rating, parâmetro Platt, snapshot ou resultado científico foi alterado
pela migração.

## Cadeia de suprimentos

As URLs e hashes dos wheels estão travados em `pyproject.toml`, `uv.lock`,
`docs/SUPPLY_CHAIN_HASHES.md` e nos testes de supply chain.

## Contratos progressivos

`ScientificState` foi adotado imediatamente. `DataAcquisitionCharter`,
`DatasetFreeze` e `SourceQualityScorecard` não são preenchidos artificialmente
nesta migração: o freeze formal exige hashes separados das partições IS/OOS e
o scorecard exige medições reais de disponibilidade, latência e cobertura.
Esses contratos devem ser materializados em um ciclo de governança próprio,
sem inventar dados retroativos. O protocolo SHA-256 existente continua sendo a
âncora verificável do dataset canônico.

O reuso de `RatingBook` foi deliberadamente adiado porque mudaria a camada
numérica recém-canonizada e exigiria novo replay científico.
