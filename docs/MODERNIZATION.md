# Modernization contract

Python 3.13 is the production baseline; 3.14 is experimental. `pyproject.toml`
and `uv.lock` are authoritative. `predictor-core==2.2.0` and
`predictor-ops==3.0.0` must be installed artifacts, never workspace imports.
Operational outcomes use `RunStatus`; scientific governance uses the separate
`ScientificState` contract carried opaquely by the runner.

## Boundaries

Sports data uses `CS_SPORTS_DB_URL`; market evidence uses a distinct
`CS_MARKET_DB_URL`. Startup rejects equal URLs. Market-shadow executable code
was moved unchanged to `docs/evidence/market_shadow`; the signed closure record
remains in `docs/records/beyond_market_closure.json`. No operational setting can
change `CLOSED_BY_HUMAN_DECISION`.

The upstream contract is `schemas/upstream-event-v1.schema.json`. File, object
storage, and queue adapters validate the same Pydantic model before persistence.
The repository interface is ready for an aggregator PostgreSQL adapter; JSONL is
only the local/offline adapter. Idempotency is enforced by the contract key.

## Shared-contract gap

The published wheels `predictor-core 2.2.0` and `predictor-ops 3.0.0` do not
export `PredictorPlugin`, `CollectorPlugin`, `SettlementPlugin`, or
`HealthProvider`. The domain therefore exports the concrete entry point
`predictor.plugins: cs = src.plugin:CsPredictorPlugin` but does not duplicate
the missing shared interfaces. Integration can add inheritance when a future
shared release publishes those contracts.

## Migration

1. Stop and remove legacy Task Scheduler jobs; never recreate market shadow.
2. Install the wheel plus shared wheels in a clean Python 3.13 environment.
3. Configure separate database URLs and one upstream transport.
4. Validate/replay upstream input; duplicate keys are ignored.
5. Run the canonical declarative job with `cs-scheduler`. The systemd timer is
   only an adapter that invokes this same portable runner.

Plugin conformance is structural: contract tests require domain identity,
`predict`, `collect`, `settle`, `health`, capabilities, metadata/provenance and
canonical states/errors. Nominal inheritance will be adopted when the aggregator
publishes `predictor_contracts`; it is not a runtime blocker.

Legacy vendor, sibling-tools integration, Task Scheduler payloads, and market
runtime are retained only under `docs/evidence` for audit history.
