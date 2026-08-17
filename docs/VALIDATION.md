# Validation record

Latest full validation: 2026-08-09 (`v3.1.0` release candidate).

> **Doc-currency update (2026-08-17):** the migration to `predictor-core==2.3.0`
> and `predictor-ops==3.1.0` (commit `e02d9064a6fa6d639d419bbb8e682420d2544e7d`,
> "Migrate to Core 2.3 and Ops 3.1") landed after the record below was written.
> The `predictor_core==2.2.1`/`predictor_ops==3.0.0` figures below have been
> corrected to the versions actually installed today. This edit only fixes
> stale version numbers; it does not re-run the full infrastructure
> homologation (Docker/Trivy/Gitleaks/SBOM) described below. As a currency
> check, `uv run pytest tests/test_supply_chain.py tests/test_modernization_contracts.py`
> passed cleanly against the current lockfile on 2026-08-17, confirming the
> installed `predictor-ops` wheel hash and version (`3.1.0`) match `uv.lock`.

## Green gates

- Python 3.13.14: 416 tests passed, zero skips, with `ResourceWarning` and
  `PytestUnraisableExceptionWarning` promoted to errors.
- Branch coverage: homologated runtime 85%; new code 89%; both exceed the 80%
  gate. Global coverage is reported without hidden omissions (79%).
- `ruff` passes for the modernized runtime surface and `pyright` reports zero
  errors. The repository-wide Ruff run exposes 227 pre-existing findings in
  legacy scientific scripts/tests; these are visible debt, not silently waived.
- Wheel and sdist build successfully. The wheel contains `jobs.json`, typed
  configuration defaults, team data, and calibration resources.
- A fresh external Python 3.13 environment installed the domain wheel plus the
  published `predictor_core==2.3.0` and `predictor_ops==3.1.0` wheels. Imports were
  verified under `site-packages`; health, scheduler validation, and a dry-run
  prediction all succeeded outside the checkout.
- The delivered runtime dependency tree has no known vulnerabilities according
  to `pip-audit`. Private/local packages are recorded as unauditable by PyPI.
- CI generates a CycloneDX runtime SBOM for every published revision.
- `git diff --check` passes.

## Infrastructure homologation

- The host had 35.85 GB free before homologation. Worktree diffs and generated
  artifacts were readable and `git diff --check` remained clean after the prior
  `ENOSPC` incident.
- Python 3.14.6: the same 138 tests passed with zero skips and resource warnings
  promoted to errors.
- The four golden tests (Elo, series, map series, and calibration) passed.
  Permanent market-shadow closure tests passed and health/plugin metadata expose
  `CLOSED_BY_HUMAN_DECISION`.
- Docker 26 built the image from scratch with `--no-cache --pull`. Container
  smokes passed for UID 100/GID 101, read-only root filesystem, active healthcheck,
  canonical prediction CLI, structural plugin discovery, portable scheduler,
  and graceful SIGTERM shutdown with exit code zero.
- Gitleaks 8.30.1 scanned 75 commits with no leaks. A narrowly scoped policy
  exception covers one historical vendor-manifest SHA-256 that the generic API
  key rule misclassified; it does not suppress a commit or repository globally.
- Trivy filesystem scanning passed with zero HIGH/CRITICAL vulnerabilities and
  zero Dockerfile misconfigurations.
- CycloneDX CLI validated `dist/sbom-python.cdx.json` as specification 1.6 with
  88 components and the final image SBOM as specification 1.7 with 55 components.
- Runtime `pip-audit` reported no known vulnerabilities. The three local wheels
  are not published on PyPI and are explicitly reported as unauditable there.
- Runtime/source scans found no vendor directory, `PYTHONPATH`, `sys.path`,
  `tools.*`, sibling-tools reference, or absolute developer-machine path.

## OS-surface remediation

The rejected Bookworm base, builder, and runtime each had the same 18 HIGH and
6 CRITICAL OS findings. Trixie had 19 HIGH and 4 CRITICAL. The selected pinned
Python 3.13 Alpine 3.24.1 base provides musllinux wheels for all native
dependencies and passed the complete 138-test suite plus golden and operational
smokes. The final real multi-stage image contains 29 OS packages (down from 97),
no build/runtime package-manager tools or caches, and Trivy reports zero HIGH,
zero CRITICAL, and zero Python findings. No vulnerability was ignored,
allowlisted, or reclassified during this remediation. Full evidence and the
per-CVE action table are in `artifacts/security/SECURITY_REMEDIATION.md`.

The 2026-08-09 local release audit additionally reproduced the sealed cutoff
database (`747b0907...72b40`, 17,169 matches), H1 (Brier 0.4537, accuracy 62.3%)
and H2 (Brier 0.4525, DM p=0.00324) in read-only mode. A clean external virtual
environment installed `cs-predictor==3.1.0`, `predictor-core==2.3.0`, and
`predictor-ops==3.1.0`; plugin discovery and scheduler validation passed.
Settlement remained fail-closed and prediction/ingestion remained laboratory-only.

The `RatingBook` adoption replay processed all 17,169 canonical series and
matched all 1,233 final team ratings exactly after rounding to the canonical
artifact precision. H1 remained Brier 0.4537 and accuracy 62.3%; no canonical
artifact was rewritten.

The local Docker daemon was unavailable during this release audit. Container
build, smoke, SBOM, and vulnerability gates therefore remain authoritative in
GitHub Actions; the earlier Docker 26 homologation above remains historical
evidence, not a claim that the current image was built locally.

Homologated status: `READY`, subject to the required green CI run for the exact
published commit.
