# Container OS security remediation

Scan date: 2026-08-02. Scanner: Trivy, HIGH/CRITICAL fail-closed, with no
ignore rules, allowlists, or severity overrides.

The JSON reports retain every Trivy `Result`, vulnerability, package, version,
status, layer and image digest. `Metadata.ImageConfig` was removed because it
duplicates the official Python image's public GPG signing key and causes secret
scanners to misclassify that public key as an API secret; it contains no scan
finding and is available independently from the recorded immutable base digest.

## Stage provenance

The pure Bookworm base, Bookworm builder, and old Bookworm runtime each contain
the same 24 HIGH/CRITICAL findings. Their Debian package inventories are also
identical (97 packages). Therefore every finding originated in the base image;
none entered through a Dockerfile-installed OS package, leaked build tool, or
Python dependency. Complete machine-readable evidence is in
`base-bookworm.json`, `builder-bookworm.json`, and `runtime-bookworm.json`.

## Actionable findings in the rejected image

`—` under fixed version means the scanner/distribution published no corrected
version. “Required” describes this application, not whether Debian itself needs
the package.

| VulnerabilityID | Severity | Package | Installed | Fixed | Fix status | Origin | Runtime required | Path/use | Action |
|---|---|---|---|---|---|---|---|---|---|
| CVE-2023-45853 | CRITICAL | zlib1g | 1:1.2.13.dfsg-1 | — | will_not_fix | base image | yes | shared compression library reachable through Python/native wheels | replace base; Alpine supplies a non-affected zlib |
| CVE-2025-69720 | HIGH | libncursesw6 | 6.4-4 | — | affected | base image | no | terminal UI support, unused by non-interactive service | replace base/remove package family |
| CVE-2025-69720 | HIGH | libtinfo6 | 6.4-4 | — | affected | base image | no | terminal capability support | replace base/remove package family |
| CVE-2025-69720 | HIGH | ncurses-base | 6.4-4 | — | affected | base image | no | terminal definitions | replace base/remove package family |
| CVE-2025-69720 | HIGH | ncurses-bin | 6.4-4 | — | affected | base image | no | terminal diagnostic utilities | replace base/remove package family |
| CVE-2025-7458 | CRITICAL | libsqlite3-0 | 3.40.1-2+deb12u2 | — | affected | base image | yes | Python sqlite3 used for Sports DB | replace base; validate SQLite behavior in full suite |
| CVE-2026-13221 | CRITICAL | perl-base | 5.36.0-7+deb12u3 | — | affected | base image | no | scripting runtime unused by application | replace base/remove Perl |
| CVE-2026-41992 | HIGH | gzip | 1.12-1 | — | fix_deferred | base image | no | archive CLI unused at runtime | replace base/remove gzip CLI |
| CVE-2026-42496 | CRITICAL | perl-base | 5.36.0-7+deb12u3 | — | fix_deferred | base image | no | scripting runtime unused by application | replace base/remove Perl |
| CVE-2026-42497 | HIGH | perl-base | 5.36.0-7+deb12u3 | — | fix_deferred | base image | no | scripting runtime unused by application | replace base/remove Perl |
| CVE-2026-48962 | HIGH | perl-base | 5.36.0-7+deb12u3 | — | affected | base image | no | scripting runtime unused by application | replace base/remove Perl |
| CVE-2026-53615 | HIGH | bsdutils | 1:2.38.1-5+deb12u3 | — | affected | base image | no | OS command-line utilities unused by service | replace base/remove util-linux suite |
| CVE-2026-53615 | HIGH | libblkid1 | 2.38.1-5+deb12u3 | — | affected | base image | no | block-device discovery unreachable in container workload | replace base/remove util-linux suite |
| CVE-2026-53615 | HIGH | libmount1 | 2.38.1-5+deb12u3 | — | affected | base image | no | mount support unreachable; container has read-only root | replace base/remove util-linux suite |
| CVE-2026-53615 | HIGH | libsmartcols1 | 2.38.1-5+deb12u3 | — | affected | base image | no | CLI column formatting unused | replace base/remove util-linux suite |
| CVE-2026-53615 | HIGH | libuuid1 | 2.38.1-5+deb12u3 | — | affected | base image | no | util-linux UUID library not imported by application | replace base/remove util-linux suite |
| CVE-2026-53615 | HIGH | mount | 2.38.1-5+deb12u3 | — | affected | base image | no | privileged mount command unreachable as non-root | replace base/remove util-linux suite |
| CVE-2026-53615 | HIGH | util-linux | 2.38.1-5+deb12u3 | — | affected | base image | no | administrative commands unused by service | replace base/remove util-linux suite |
| CVE-2026-53615 | HIGH | util-linux-extra | 2.38.1-5+deb12u3 | — | affected | base image | no | diagnostic/administrative commands unused | replace base/remove util-linux suite |
| CVE-2026-54369 | HIGH | libacl1 | 2.3.1-3 | — | fix_deferred | base image | no | ACL manipulation unused; runtime is non-root/read-only | replace base/remove ACL tooling |
| CVE-2026-57432 | HIGH | perl-base | 5.36.0-7+deb12u3 | — | affected | base image | no | scripting runtime unused by application | replace base/remove Perl |
| CVE-2026-57433 | CRITICAL | perl-base | 5.36.0-7+deb12u3 | — | affected | base image | no | scripting runtime unused by application | replace base/remove Perl |
| CVE-2026-8376 | CRITICAL | perl-base | 5.36.0-7+deb12u3 | — | affected | base image | no | scripting runtime unused by application | replace base/remove Perl |
| CVE-2026-9538 | HIGH | perl-base | 5.36.0-7+deb12u3 | — | fix_deferred | base image | no | scripting runtime unused by application | replace base/remove Perl |

The final Alpine base/runtime contains none of these CVEs, so no risk acceptance
request is required and no residual CVE is being approved.

## Base comparison

All three candidates used Python 3.13.14, resolved the same application package
versions, ran 138 tests with zero skips, and preserved all four golden outputs.
Test-only Git/pytest installations were ephemeral and never copied to runtime.

| Candidate | Pinned digest | Base size | Final size | HIGH | CRITICAL | Wheels | Build | 138 tests / golden | Plugin / scheduler / health / read-only / SIGTERM |
|---|---|---:|---:|---:|---:|---|---:|---|---|
| Debian 12 Bookworm slim | `sha256:9d7f287598e1a5a978c015ee176d8216435aaf335ed69ac3c38dd1bbb10e8d64` | 120.8 MB | 455.1 MB | 18 | 6 | manylinux compatible | 33.2 s | pass / pass | pass / pass / pass / pass / pass |
| Debian 13 Trixie slim | `sha256:6771159cd4fa5d9bba1258caf0b82e6b73458c694d178ad97c5e925c2d0e1a91` | 117.9 MB | 452.1 MB | 19 | 4 | manylinux compatible | 36.49 s | pass / pass | pass / pass / pass / pass / pass |
| Alpine 3.24.1 minimal | `sha256:399babc8b49529dabfd9c922f2b5eea81d611e4512e3ed250d75bd2e7683f4b0` | 45.4 MB | 395.5 MB | 0 | 0 | musllinux wheels proven for NumPy, SciPy, pandas, curl_cffi, CFFI, PyYAML, and Pydantic | 41.84 s | pass / pass | pass / pass / pass / pass / pass |

Alpine was selected because it is the smallest compatible base and the only
candidate meeting the zero HIGH/CRITICAL criterion. This is not an assumed musl
migration: the complete tests, golden outputs, plugin, scheduler, healthcheck,
read-only operation, and shutdown behavior were executed on musl.

## Dockerfile and runtime inventory audit

- Real multi-stage build: build frontend and pip exist only in `builder`; runtime
  receives `/opt/venv` and two read-only configuration/data files.
- No OS packages are installed by the Dockerfile, so there are no `apt` packages
  to justify and no recommends. Alpine base and final runtime both contain the
  same 29 OS packages; exact lists are `packages-base-alpine.txt` and
  `packages-runtime-final.txt`.
- Runtime lookup found none of: gcc/g++, make, build-essential, Git, curl/wget,
  pkg-config, headers/dev tools, uv, pip/build, cc/ld/as, gdb/strace, bash, or the
  apk executable.
- Runtime cache inspection found no files under `/root/.cache`, `/var/cache/apk`,
  or `/tmp`.
- Healthcheck uses `cs-predictor health` implemented in Python; it installs no
  HTTP or shell utility.

## Evidence index

- Rejected Bookworm: `base-bookworm.json`, `builder-bookworm.json`,
  `runtime-bookworm.json` and matching package inventories.
- Trixie comparison: `base-trixie.json` and `Dockerfile.trixie-candidate`.
- Selected Alpine: `base-alpine.json`, `builder-alpine.json`,
  `runtime-final.json`, package inventories, and `Dockerfile.alpine-candidate`.
- Final image SBOM: `sbom-image-final.cdx.json` (CycloneDX 1.7, validated).
