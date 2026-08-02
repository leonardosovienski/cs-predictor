# Supply-chain inventory

| Artifact | Version | SHA-256 |
|---|---:|---|
| `wheelhouse/predictor_core-2.1.0-py3-none-any.whl` | 2.1.0 | `83de1d4415700dedaf387bc46dd9685e046de1fa47f37367bf2167462b09761b` |
| `wheelhouse/predictor_ops-2.0.1-py3-none-any.whl` | 2.0.1 | `37de983718b318fc1ccadc6b299db9fccdbea946080a2b710d6dd6a939a7e766` |
| `docs/records/beyond_market_closure.json` | cs-beyond-market-closure/1.1 | `e30603fae444c7c88aced505a966946e34106f07c17e906c5d8b18c0bdde5903` |
| `dist/cs_predictor-2.0.0-py3-none-any.whl` | 2.0.0 | `0a53988391dbe5cfe86306c7b999bce15aea4f50ac02bc3c2d8eb819731b4bf0` |
| `dist/cs_predictor-2.0.0.tar.gz` | 2.0.0 | `85226b5a350d32cd1b27763cd87a105f3907e56a8233398abb64b8fd3d020919` |
| `dist/sbom-python.cdx.json` | CycloneDX 1.6 | `58510979ac7e96bd221500084e4854cd6b25fe731dfcc15a3cdf5a97fce6722f` |
| `artifacts/security/sbom-image-final.cdx.json` | CycloneDX 1.7 | `c945be96b49a3989f5cf37682b84bc543138384af3c55d9021ba0441fff5ab25` |
| `artifacts/security/runtime-final.json` | Trivy JSON | `658ed7d40ce8d165c6b604e3891d1fdd36fc03474865c138f521bcfbf605ecf4` |
| `Dockerfile` | Python 3.13 / Alpine 3.24.1 | `78ae2c8ef80d0899475fefed02d986afdf8d8ba1a618e33b3990e6abddde41bf` |
| `python:3.13-alpine` | base image | `sha256:399babc8b49529dabfd9c922f2b5eea81d611e4512e3ed250d75bd2e7683f4b0` |
| `cs-predictor:homologated-20260802` | local image ID | `sha256:849b96c99c1c8fb551020802a15c53526b9d978c8214b6c87a2c0984240c9784` |

`uv.lock` records all resolved package hashes. CI generates CycloneDX JSON for
the wheel environment and an SPDX JSON SBOM for the container image.
