# Supply-chain inventory

| Artifact | Version | SHA-256 |
|---|---:|---|
| GitHub release `predictor_core-2.2.0-py3-none-any.whl` | 2.2.0 | `fe95dece93a2c91436ffd60058cea1d9192022d2170abb7e8e8512ccb76f9fdd` |
| GitHub release `predictor_ops-3.0.0-py3-none-any.whl` | 3.0.0 | `9574d5fa4d17232a9d7dbd1aaff0131b65f341974508c5457b8d570bf41e8945` |
| `docs/records/beyond_market_closure.json` | cs-beyond-market-closure/1.1 | `e30603fae444c7c88aced505a966946e34106f07c17e906c5d8b18c0bdde5903` |
| `dist/cs_predictor-3.0.1-py3-none-any.whl` | 3.0.1 | `2d2bde71928d8c218c34f46e81eb6dfa9a25f3a2923002b49f84687bd64ecf35` |
| `Dockerfile` | Python 3.13 / Alpine 3.24.1 | `7fdd44bbb73ac0580d633e57f9fdc65e8f37f8ab9bc4ce9984fb2d233f86ec39` |
| `python:3.13-alpine` | base image | `sha256:399babc8b49529dabfd9c922f2b5eea81d611e4512e3ed250d75bd2e7683f4b0` |
| `cs-predictor:homologated-20260802` | local image ID | `sha256:849b96c99c1c8fb551020802a15c53526b9d978c8214b6c87a2c0984240c9784` |

`uv.lock` records all resolved package hashes. CI generates the sdist, a
CycloneDX JSON SBOM for the wheel environment, and an SPDX JSON SBOM for the
container image. Their digests belong to the immutable release/CI artifacts;
they are not self-recorded here because the sdist contains this document.
