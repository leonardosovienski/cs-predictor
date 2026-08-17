# Supply-chain inventory

Current as of 2026-08-17, matching `uv.lock` after the migration in commit
`e02d9064a6fa6d639d419bbb8e682420d2544e7d` ("Migrate to Core 2.3 and Ops 3.1").

| Artifact | Version | SHA-256 |
|---|---:|---|
| GitHub release `predictor_core-2.3.0-py3-none-any.whl` | 2.3.0 | `e0d29eac348e2be4092dde1b629c101d54973b54b5d43014cdaee69e4e17b3b9` |
| GitHub release `predictor_ops-3.1.0-py3-none-any.whl` | 3.1.0 | `490ece696f9173bbaa56c2c53a1ff6e5ffab1a7625fb00ac0a5f896c37081b37` |
| `docs/records/beyond_market_closure.json` | cs-beyond-market-closure/1.1 | `e30603fae444c7c88aced505a966946e34106f07c17e906c5d8b18c0bdde5903` |
| `dist/cs_predictor-3.1.0-py3-none-any.whl` | 3.1.0 | `18682491cbe578d8e8c3e638a09930121efbf7f5f1226b6466bc78a6c726f4f0` |
| `Dockerfile` | Python 3.13 / Alpine 3.24.1 | `113d82d03e840c2cd775d6f149aad73f67322473f9cb760070defd3f727d1067` |
| `python:3.13-alpine` | base image | `sha256:399babc8b49529dabfd9c922f2b5eea81d611e4512e3ed250d75bd2e7683f4b0` |
| `cs-predictor:homologated-20260802` | local image ID | `sha256:849b96c99c1c8fb551020802a15c53526b9d978c8214b6c87a2c0984240c9784` |

`uv.lock` records all resolved package hashes. CI generates the sdist, a
CycloneDX JSON SBOM for the wheel environment, and an SPDX JSON SBOM for the
container image. Their digests belong to the immutable release/CI artifacts;
they are not self-recorded here because the sdist contains this document.
