# P4-CS temporal contract prototype

This test-only experiment adapts the canonical `PRE_EVENT` and `MATURED`
snapshots from `src/cs_snapshots.py`. It does not reopen the scientific
verdict, call external services, or change production pipelines, models,
ratings, datasets, Core, Ops, or persisted schemas.

The CS cutoff is the scheduled series start. Result availability is the
canonical `result_retrieved_at_utc`; maturation cannot precede it. The
PRE_EVENT payload cannot contain post-event fields, and MATURED must retain
the event identity and exact predecessor hash. The golden metric is the
domain's native squared error for the probability assigned to the winner.

| Concern | Classification |
|---|---|
| aware prediction/maturity and replay | `CORE_CONTRACT_SUFFICIENT` |
| snapshot link, result availability and transition checks | `CONSUMER_ADAPTER_REQUIRED` |
| canonical JSON/hash helper | `POSSIBLE_FUTURE_CORE_CANDIDATE` |
| BO format, maps, teams and winner Brier | `DOMAIN_SPECIFIC` |
| result retrieval versus actual publication time | `SEMANTIC_CONFLICT` unless explicit locally |

This pilot proves deterministic offline temporal integrity only. It does not
prove live publication latency, scientific quality, market value, or metric
equivalence across domains. No Core/Ops extraction is proposed here.
