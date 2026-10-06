# Interop run report

## Header

- **Run ID:** `2026-10-07T01.06.54Z`
- **Generated:** 2026-10-07T01:19:07Z
- **Started:** 2026-10-07T01:06:54Z
- **Ended:** 2026-10-07T01:19:07Z
- **Duration:** 733.0s
- **Invocation:** `./run.sh all`
- **Test repo git commit hash:** `dc71b417b72b8088d1e147ac2ab1d0854bc757d1` on `main` (dirty)
- **Catalog submodule:** `f6988945121bc9f63b34a70ddc59e6881fc0ba82`
- **Host:** x86_64 / Linux 7.0.0-34-generic; cpus=22; docker=Docker version 29.1.3, build 29.1.3-0ubuntu3~24.04.2; compose=Docker Compose version 2.40.3+ds1-0ubuntu1~24.04.1

## Verdicts

| Unit | Controller | VDR | VDG | Resolver | Verdict | Passed | Expected | Duration | Repro |
|------|------------|-----|-----|----------|---------|--------|----------|----------|-------|
| `matrix:1` | python | python | none | python | PASS | 1 | 1 | 8.7s | `./run.sh matrix 1` |
| `matrix:2` | python | python | rust | python | PASS | 1 | 1 | 9.9s | `./run.sh matrix 2` |
| `matrix:3` | python | python | none | rust | PASS | 1 | 1 | 9.6s | `./run.sh matrix 3` |
| `matrix:4` | python | python | rust | rust | PASS | 1 | 1 | 6.8s | `./run.sh matrix 4` |
| `matrix:5` | python | rust | none | python | PASS | 1 | 1 | 8.6s | `./run.sh matrix 5` |
| `matrix:6` | python | rust | rust | python | PASS | 1 | 1 | 9.7s | `./run.sh matrix 6` |
| `matrix:7` | python | rust | none | rust | PASS | 1 | 1 | 5.4s | `./run.sh matrix 7` |
| `matrix:8` | python | rust | rust | rust | PASS | 1 | 1 | 6.6s | `./run.sh matrix 8` |
| `matrix:9` | rust | python | none | python | PASS | 1 | 1 | 8.0s | `./run.sh matrix 9` |
| `matrix:10` | rust | python | rust | python | PASS | 1 | 1 | 9.4s | `./run.sh matrix 10` |
| `matrix:11` | rust | python | none | rust | PASS | 1 | 1 | 4.8s | `./run.sh matrix 11` |
| `matrix:12` | rust | python | rust | rust | PASS | 1 | 1 | 6.2s | `./run.sh matrix 12` |
| `matrix:13` | rust | rust | none | python | PASS | 1 | 1 | 7.8s | `./run.sh matrix 13` |
| `matrix:14` | rust | rust | rust | python | PASS | 1 | 1 | 9.5s | `./run.sh matrix 14` |
| `matrix:15` | rust | rust | none | rust | PASS | 1 | 1 | 4.7s | `./run.sh matrix 15` |
| `matrix:16` | rust | rust | rust | rust | PASS | 1 | 1 | 6.1s | `./run.sh matrix 16` |
| `matrix:17` | python | python | none | zkred | PASS | 1 | 1 | 5.8s | `./run.sh matrix 17` |
| `matrix:18` | python | python | rust | zkred | PASS | 1 | 1 | 7.1s | `./run.sh matrix 18` |
| `matrix:19` | rust | rust | none | zkred | PASS | 1 | 1 | 5.2s | `./run.sh matrix 19` |
| `matrix:20` | rust | rust | rust | zkred | PASS | 1 | 1 | 6.7s | `./run.sh matrix 20` |
| `matrix:21` | zkred | python | none | python, rust | PASS | 1 | 1 | 9.4s | `./run.sh matrix 21` |
| `matrix:22` | zkred | rust | none | python, rust | PASS | 1 | 1 | 9.5s | `./run.sh matrix 22` |
| `vectors:python` | none | test-vector-server | none | python | PASS | 302 | 302 | 82.2s | `./run.sh vectors --resolver python` |
| `vectors:rust` | none | test-vector-server | none | rust | PASS | 302 | 302 | 21.1s | `./run.sh vectors --resolver rust` |
| `vectors:zkred` | none | test-vector-server | none | zkred | FAIL | 298 | 302 | 33.1s | `./run.sh vectors --resolver zkred` |
| `scenarios:python` | none | test-vector-server | none | python | FAIL | 1 | 19 | 28.6s | `./run.sh scenarios --resolver python` |
| `scenarios:rust` | none | test-vector-server | none | rust | PASS | 19 | 19 | 11.0s | `./run.sh scenarios --resolver rust` |
| `scenarios:zkred` | none | test-vector-server | none | zkred | FAIL | 0 | 19 | 9.4s | `./run.sh scenarios --resolver zkred` |

## Invoked components

- **controller/python:** did-webplus-python-cli — image ID `sha256:605c16158fb9e810513d9ea798af4d776dbbfa415cae0b18d610539896f3ba02` (from this repo)
- **controller/rust:** ghcr.io/ledgerdomain/did-webplus-cli:v0.6.0 — image ID `sha256:85dd882311482731d592fabbc06d36120ed892f5448853e085271ab775f31fdf`
- **controller/zkred:** did-webplus-zkred — image ID `sha256:e6e443e5204d742182d9462dccb4ec5951ad33427eb2aab16e5cd5aa3bc742fd` (from this repo, zkred pin `0.9.1`)
- **resolver/python:** did-webplus-python-cli — image ID `sha256:605c16158fb9e810513d9ea798af4d776dbbfa415cae0b18d610539896f3ba02` (from this repo)
- **resolver/rust:** ghcr.io/ledgerdomain/did-webplus-cli:v0.6.0 — image ID `sha256:85dd882311482731d592fabbc06d36120ed892f5448853e085271ab775f31fdf`
- **resolver/zkred:** did-webplus-zkred — image ID `sha256:e6e443e5204d742182d9462dccb4ec5951ad33427eb2aab16e5cd5aa3bc742fd` (from this repo, zkred pin `0.9.1`)
- **vdg/rust:** ghcr.io/ledgerdomain/did-webplus-vdg:v0.6.0 — image ID `sha256:d86a35e97202ccd225469c1ec64a4d3ecb16dce6bb4a238a50f42ce17e9c5fa4`
- **vdr/python:** interop-python-vdr — image ID `sha256:5829fa6e85d3a07e9b784da0872d02cb78e11f4ff5a5915309d04d81948b4ec2` (from this repo)
- **vdr/rust:** ghcr.io/ledgerdomain/did-webplus-vdr:v0.6.0 — image ID `sha256:907b3b46b7afcca74d569e67670d17b2f026e689678f70a07dec012dda70badd`
- **vdr/test-vector-server:** Built for interop testing; serves the test-vector catalog at ledgerdomain.github.io/did-webplus-spec/test-vector — image ID `sha256:e20ac991342d919691f94229a26acb730cd85d014759ab3629e8a4f489f98a1b` (catalog submodule `f6988945121bc9f63b34a70ddc59e6881fc0ba82`)

## Failures

### `vectors:zkred` — non-root-self-hash-inconsistent-slots

- **Roles:** controller=none, vdr=test-vector-server, vdg=none, resolver=zkred
- **Detail:** valid==false: resolve must fail, but succeeded with versionId=1
- **Case repro:** `./run.sh vectors --resolver zkred --name non-root-self-hash-inconsistent-slots --catalog-url http://ledgerdomain.github.io/did-webplus-spec/test-vector --timeout 60.0 --jobs 8`
- **Suite log:** `logs/vectors.log` (docker run reproducers are in the tee'd log)

### `vectors:zkred` — non-root-vm-id-self-hash-mismatch

- **Roles:** controller=none, vdr=test-vector-server, vdg=none, resolver=zkred
- **Detail:** valid==false: resolve must fail, but succeeded with versionId=1
- **Case repro:** `./run.sh vectors --resolver zkred --name non-root-vm-id-self-hash-mismatch --catalog-url http://ledgerdomain.github.io/did-webplus-spec/test-vector --timeout 60.0 --jobs 8`
- **Suite log:** `logs/vectors.log` (docker run reproducers are in the tee'd log)

### `vectors:zkred` — non-root-vm-id-self-hash-mismatch-one-of-many

- **Roles:** controller=none, vdr=test-vector-server, vdg=none, resolver=zkred
- **Detail:** valid==false: resolve must fail, but succeeded with versionId=1
- **Case repro:** `./run.sh vectors --resolver zkred --name non-root-vm-id-self-hash-mismatch-one-of-many --catalog-url http://ledgerdomain.github.io/did-webplus-spec/test-vector --timeout 60.0 --jobs 8`
- **Suite log:** `logs/vectors.log` (docker run reproducers are in the tee'd log)

### `vectors:zkred` — non-root-vm-kid-self-hash-mismatch

- **Roles:** controller=none, vdr=test-vector-server, vdg=none, resolver=zkred
- **Detail:** valid==false: resolve must fail, but succeeded with versionId=1
- **Case repro:** `./run.sh vectors --resolver zkred --name non-root-vm-kid-self-hash-mismatch --catalog-url http://ledgerdomain.github.io/did-webplus-spec/test-vector --timeout 60.0 --jobs 8`
- **Suite log:** `logs/vectors.log` (docker run reproducers are in the tee'd log)

### `scenarios:python` — cold-plain-did-no-metadata

- **Roles:** controller=none, vdr=test-vector-server, vdg=none, resolver=python
- **Detail:** didDocumentMetadata mismatch: expected {"updated": "2025-01-01T00:00:03Z", "updatedMilliseconds": "2025-01-01T00:00:03.875Z", "versionId": "3"}, got {"deactivated": false, "updated": "2025-01-01T00:00:03.875Z", "versionId": 3}; didResolutionMetadata.fetchedUpdatesFromVDR: expected True, got None; didResolutionMetadata.didDocumentMetadataResolvedLocally: expected True, got False
- **Case repro:** `./run.sh scenarios --resolver python --name cold-plain-did-no-metadata --catalog-url http://ledgerdomain.github.io/did-webplus-spec/test-vector --timeout 60.0`
- **Suite log:** `logs/scenarios.log` (docker run reproducers are in the tee'd log)

### `scenarios:python` — conflict-via-local-self-hash

- **Roles:** controller=none, vdr=test-vector-server, vdg=none, resolver=python
- **Detail:** didDocumentMetadata mismatch: expected {"updated": "2025-01-01T00:00:03Z", "updatedMilliseconds": "2025-01-01T00:00:03.875Z", "versionId": "3"}, got {"deactivated": false, "updated": "2025-01-01T00:00:03.875Z", "versionId": 3}; didResolutionMetadata.fetchedUpdatesFromVDR: expected True, got None; didResolutionMetadata.didDocumentMetadataResolvedLocally: expected True, got False
- **Case repro:** `./run.sh scenarios --resolver python --name conflict-via-local-self-hash --catalog-url http://ledgerdomain.github.io/did-webplus-spec/test-vector --timeout 60.0`
- **Suite log:** `logs/scenarios.log` (docker run reproducers are in the tee'd log)

### `scenarios:python` — conflicting-query-params

- **Roles:** controller=none, vdr=test-vector-server, vdg=none, resolver=python
- **Detail:** didDocumentMetadata mismatch: expected {"updated": "2025-01-01T00:00:03Z", "updatedMilliseconds": "2025-01-01T00:00:03.875Z", "versionId": "3"}, got {"deactivated": false, "updated": "2025-01-01T00:00:03.875Z", "versionId": 3}; didResolutionMetadata.fetchedUpdatesFromVDR: expected True, got None; didResolutionMetadata.didDocumentMetadataResolvedLocally: expected True, got False
- **Case repro:** `./run.sh scenarios --resolver python --name conflicting-query-params --catalog-url http://ledgerdomain.github.io/did-webplus-spec/test-vector --timeout 60.0`
- **Suite log:** `logs/scenarios.log` (docker run reproducers are in the tee'd log)

### `scenarios:python` — deactivated-all-local

- **Roles:** controller=none, vdr=test-vector-server, vdg=none, resolver=python
- **Detail:** didDocumentMetadata mismatch: expected {"deactivated": true, "updated": "2025-01-01T00:00:03Z", "updatedMilliseconds": "2025-01-01T00:00:03.875Z", "versionId": "3"}, got {"deactivated": true, "updated": "2025-01-01T00:00:03.875Z", "versionId": 3}; didResolutionMetadata.fetchedUpdatesFromVDR: expected True, got None; didResolutionMetadata.didDocumentMetadataResolvedLocally: expected True, got False
- **Case repro:** `./run.sh scenarios --resolver python --name deactivated-all-local --catalog-url http://ledgerdomain.github.io/did-webplus-spec/test-vector --timeout 60.0`
- **Suite log:** `logs/scenarios.log` (docker run reproducers are in the tee'd log)

### `scenarios:python` — deactivated-known-absence

- **Roles:** controller=none, vdr=test-vector-server, vdg=none, resolver=python
- **Detail:** didDocumentMetadata mismatch: expected {"deactivated": true, "updated": "2025-01-01T00:00:03Z", "updatedMilliseconds": "2025-01-01T00:00:03.875Z", "versionId": "3"}, got {"deactivated": true, "updated": "2025-01-01T00:00:03.875Z", "versionId": 3}; didResolutionMetadata.fetchedUpdatesFromVDR: expected True, got None; didResolutionMetadata.didDocumentMetadataResolvedLocally: expected True, got False
- **Case repro:** `./run.sh scenarios --resolver python --name deactivated-known-absence --catalog-url http://ledgerdomain.github.io/did-webplus-spec/test-vector --timeout 60.0`
- **Suite log:** `logs/scenarios.log` (docker run reproducers are in the tee'd log)

### `scenarios:python` — fetch-failed-with-local-document

- **Roles:** controller=none, vdr=test-vector-server, vdg=none, resolver=python
- **Detail:** didDocumentMetadata mismatch: expected {"updated": "2025-01-01T00:00:03Z", "updatedMilliseconds": "2025-01-01T00:00:03.875Z", "versionId": "3"}, got {"deactivated": false, "updated": "2025-01-01T00:00:03.875Z", "versionId": 3}; didResolutionMetadata.fetchedUpdatesFromVDR: expected True, got None; didResolutionMetadata.didDocumentMetadataResolvedLocally: expected True, got False
- **Case repro:** `./run.sh scenarios --resolver python --name fetch-failed-with-local-document --catalog-url http://ledgerdomain.github.io/did-webplus-spec/test-vector --timeout 60.0`
- **Suite log:** `logs/scenarios.log` (docker run reproducers are in the tee'd log)

### `scenarios:python` — incremental-range-fetch

- **Roles:** controller=none, vdr=test-vector-server, vdg=none, resolver=python
- **Detail:** didDocumentMetadata mismatch: expected {"versionId": "0"}, got {"created": "2025-01-01T00:00:00.001Z", "deactivated": false, "updated": "2025-01-01T00:00:00.001Z", "versionId": 0}; didResolutionMetadata.fetchedUpdatesFromVDR: expected True, got None; didResolutionMetadata.didDocumentMetadataResolvedLocally: expected True, got False
- **Case repro:** `./run.sh scenarios --resolver python --name incremental-range-fetch --catalog-url http://ledgerdomain.github.io/did-webplus-spec/test-vector --timeout 60.0`
- **Suite log:** `logs/scenarios.log` (docker run reproducers are in the tee'd log)

### `scenarios:python` — local-only-matrix

- **Roles:** controller=none, vdr=test-vector-server, vdg=none, resolver=python
- **Step:** 1
- **Detail:** didDocumentMetadata mismatch: expected {"updated": "2025-01-01T00:00:03Z", "updatedMilliseconds": "2025-01-01T00:00:03.875Z", "versionId": "3"}, got {"deactivated": false, "updated": "2025-01-01T00:00:03.875Z", "versionId": 3}; didResolutionMetadata.fetchedUpdatesFromVDR: expected True, got None; didResolutionMetadata.didDocumentMetadataResolvedLocally: expected True, got False
- **Case repro:** `./run.sh scenarios --resolver python --name local-only-matrix --catalog-url http://ledgerdomain.github.io/did-webplus-spec/test-vector --timeout 60.0`
- **Suite log:** `logs/scenarios.log` (docker run reproducers are in the tee'd log)

### `scenarios:python` — plain-did-always-fetches

- **Roles:** controller=none, vdr=test-vector-server, vdg=none, resolver=python
- **Detail:** didDocumentMetadata mismatch: expected {"updated": "2025-01-01T00:00:03Z", "updatedMilliseconds": "2025-01-01T00:00:03.875Z", "versionId": "3"}, got {"deactivated": false, "updated": "2025-01-01T00:00:03.875Z", "versionId": 3}; didResolutionMetadata.fetchedUpdatesFromVDR: expected True, got None; didResolutionMetadata.didDocumentMetadataResolvedLocally: expected True, got False
- **Case repro:** `./run.sh scenarios --resolver python --name plain-did-always-fetches --catalog-url http://ledgerdomain.github.io/did-webplus-spec/test-vector --timeout 60.0`
- **Suite log:** `logs/scenarios.log` (docker run reproducers are in the tee'd log)

### `scenarios:python` — request-creation-cold

- **Roles:** controller=none, vdr=test-vector-server, vdg=none, resolver=python
- **Detail:** unsupported options: requestCreate; didDocumentMetadata mismatch: expected {"created": "2025-01-01T00:00:00Z", "createdMilliseconds": "2025-01-01T00:00:00.001Z", "updated": "2025-01-01T00:00:03Z", "updatedMilliseconds": "2025-01-01T00:00:03.875Z", "versionId": "3"}, got {"deactivated": false, "updated": "2025-01-01T00:00:03.875Z", "versionId": 3}; didResolutionMetadata.fetchedUpdatesFromVDR: expected True, got None
- **Case repro:** `./run.sh scenarios --resolver python --name request-creation-cold --catalog-url http://ledgerdomain.github.io/did-webplus-spec/test-vector --timeout 60.0`
- **Suite log:** `logs/scenarios.log` (docker run reproducers are in the tee'd log)

### `scenarios:python` — request-creation-warm

- **Roles:** controller=none, vdr=test-vector-server, vdg=none, resolver=python
- **Detail:** didDocumentMetadata mismatch: expected {"updated": "2025-01-01T00:00:03Z", "updatedMilliseconds": "2025-01-01T00:00:03.875Z", "versionId": "3"}, got {"deactivated": false, "updated": "2025-01-01T00:00:03.875Z", "versionId": 3}; didResolutionMetadata.fetchedUpdatesFromVDR: expected True, got None; didResolutionMetadata.didDocumentMetadataResolvedLocally: expected True, got False
- **Case repro:** `./run.sh scenarios --resolver python --name request-creation-warm --catalog-url http://ledgerdomain.github.io/did-webplus-spec/test-vector --timeout 60.0`
- **Suite log:** `logs/scenarios.log` (docker run reproducers are in the tee'd log)

### `scenarios:python` — request-deactivated-forces-fetch

- **Roles:** controller=none, vdr=test-vector-server, vdg=none, resolver=python
- **Detail:** didDocumentMetadata mismatch: expected {"updated": "2025-01-01T00:00:03Z", "updatedMilliseconds": "2025-01-01T00:00:03.875Z", "versionId": "3"}, got {"deactivated": false, "updated": "2025-01-01T00:00:03.875Z", "versionId": 3}; didResolutionMetadata.fetchedUpdatesFromVDR: expected True, got None; didResolutionMetadata.didDocumentMetadataResolvedLocally: expected True, got False
- **Case repro:** `./run.sh scenarios --resolver python --name request-deactivated-forces-fetch --catalog-url http://ledgerdomain.github.io/did-webplus-spec/test-vector --timeout 60.0`
- **Suite log:** `logs/scenarios.log` (docker run reproducers are in the tee'd log)

### `scenarios:python` — request-latest-forces-fetch

- **Roles:** controller=none, vdr=test-vector-server, vdg=none, resolver=python
- **Detail:** didDocumentMetadata mismatch: expected {"updated": "2025-01-01T00:00:03Z", "updatedMilliseconds": "2025-01-01T00:00:03.875Z", "versionId": "3"}, got {"deactivated": false, "updated": "2025-01-01T00:00:03.875Z", "versionId": 3}; didResolutionMetadata.fetchedUpdatesFromVDR: expected True, got None; didResolutionMetadata.didDocumentMetadataResolvedLocally: expected True, got False
- **Case repro:** `./run.sh scenarios --resolver python --name request-latest-forces-fetch --catalog-url http://ledgerdomain.github.io/did-webplus-spec/test-vector --timeout 60.0`
- **Suite log:** `logs/scenarios.log` (docker run reproducers are in the tee'd log)

### `scenarios:python` — request-next-at-latest

- **Roles:** controller=none, vdr=test-vector-server, vdg=none, resolver=python
- **Detail:** didDocumentMetadata mismatch: expected {"updated": "2025-01-01T00:00:03Z", "updatedMilliseconds": "2025-01-01T00:00:03.875Z", "versionId": "3"}, got {"deactivated": false, "updated": "2025-01-01T00:00:03.875Z", "versionId": 3}; didResolutionMetadata.fetchedUpdatesFromVDR: expected True, got None; didResolutionMetadata.didDocumentMetadataResolvedLocally: expected True, got False
- **Case repro:** `./run.sh scenarios --resolver python --name request-next-at-latest --catalog-url http://ledgerdomain.github.io/did-webplus-spec/test-vector --timeout 60.0`
- **Suite log:** `logs/scenarios.log` (docker run reproducers are in the tee'd log)

### `scenarios:python` — request-next-with-local-next

- **Roles:** controller=none, vdr=test-vector-server, vdg=none, resolver=python
- **Detail:** didDocumentMetadata mismatch: expected {"updated": "2025-01-01T00:00:03Z", "updatedMilliseconds": "2025-01-01T00:00:03.875Z", "versionId": "3"}, got {"deactivated": false, "updated": "2025-01-01T00:00:03.875Z", "versionId": 3}; didResolutionMetadata.fetchedUpdatesFromVDR: expected True, got None; didResolutionMetadata.didDocumentMetadataResolvedLocally: expected True, got False
- **Case repro:** `./run.sh scenarios --resolver python --name request-next-with-local-next --catalog-url http://ledgerdomain.github.io/did-webplus-spec/test-vector --timeout 60.0`
- **Suite log:** `logs/scenarios.log` (docker run reproducers are in the tee'd log)

### `scenarios:python` — warm-both-params

- **Roles:** controller=none, vdr=test-vector-server, vdg=none, resolver=python
- **Detail:** didDocumentMetadata mismatch: expected {"updated": "2025-01-01T00:00:03Z", "updatedMilliseconds": "2025-01-01T00:00:03.875Z", "versionId": "3"}, got {"deactivated": false, "updated": "2025-01-01T00:00:03.875Z", "versionId": 3}; didResolutionMetadata.fetchedUpdatesFromVDR: expected True, got None; didResolutionMetadata.didDocumentMetadataResolvedLocally: expected True, got False
- **Case repro:** `./run.sh scenarios --resolver python --name warm-both-params --catalog-url http://ledgerdomain.github.io/did-webplus-spec/test-vector --timeout 60.0`
- **Suite log:** `logs/scenarios.log` (docker run reproducers are in the tee'd log)

### `scenarios:python` — warm-self-hash

- **Roles:** controller=none, vdr=test-vector-server, vdg=none, resolver=python
- **Detail:** didDocumentMetadata mismatch: expected {"updated": "2025-01-01T00:00:03Z", "updatedMilliseconds": "2025-01-01T00:00:03.875Z", "versionId": "3"}, got {"deactivated": false, "updated": "2025-01-01T00:00:03.875Z", "versionId": 3}; didResolutionMetadata.fetchedUpdatesFromVDR: expected True, got None; didResolutionMetadata.didDocumentMetadataResolvedLocally: expected True, got False
- **Case repro:** `./run.sh scenarios --resolver python --name warm-self-hash --catalog-url http://ledgerdomain.github.io/did-webplus-spec/test-vector --timeout 60.0`
- **Suite log:** `logs/scenarios.log` (docker run reproducers are in the tee'd log)

### `scenarios:python` — warm-version-id

- **Roles:** controller=none, vdr=test-vector-server, vdg=none, resolver=python
- **Detail:** didDocumentMetadata mismatch: expected {"updated": "2025-01-01T00:00:03Z", "updatedMilliseconds": "2025-01-01T00:00:03.875Z", "versionId": "3"}, got {"deactivated": false, "updated": "2025-01-01T00:00:03.875Z", "versionId": 3}; didResolutionMetadata.fetchedUpdatesFromVDR: expected True, got None; didResolutionMetadata.didDocumentMetadataResolvedLocally: expected True, got False
- **Case repro:** `./run.sh scenarios --resolver python --name warm-version-id --catalog-url http://ledgerdomain.github.io/did-webplus-spec/test-vector --timeout 60.0`
- **Suite log:** `logs/scenarios.log` (docker run reproducers are in the tee'd log)

### `scenarios:zkred` — cold-plain-did-no-metadata

- **Roles:** controller=none, vdr=test-vector-server, vdg=none, resolver=zkred
- **Detail:** didDocumentMetadata mismatch: expected {"updated": "2025-01-01T00:00:03Z", "updatedMilliseconds": "2025-01-01T00:00:03.875Z", "versionId": "3"}, got {"created": "2025-01-01T00:00:00.001Z", "latestVersionId": "3", "mode": "full", "selfHash": "uHiBSAfVnPOWQxnPE-BDuwdZM-OqAKr_71YRhq2Db-ChdOQ", "updated": "2025-01-01T00:00:03.875Z", "verified": true, "versionId": "3"}; didResolutionMetadata.fetchedUpdatesFromVDR: expected True, got None; didResolutionMetadata.didDocumentResolvedLocally: expected False, got None; didResolutionMetadata.didDocumentMetadataResolvedLocally: expected True, got None
- **Case repro:** `./run.sh scenarios --resolver zkred --name cold-plain-did-no-metadata --catalog-url http://ledgerdomain.github.io/did-webplus-spec/test-vector --timeout 60.0`
- **Suite log:** `logs/scenarios.log` (docker run reproducers are in the tee'd log)

### `scenarios:zkred` — conflict-via-local-self-hash

- **Roles:** controller=none, vdr=test-vector-server, vdg=none, resolver=zkred
- **Detail:** didDocumentMetadata mismatch: expected {"updated": "2025-01-01T00:00:03Z", "updatedMilliseconds": "2025-01-01T00:00:03.875Z", "versionId": "3"}, got {"created": "2025-01-01T00:00:00.001Z", "latestVersionId": "3", "mode": "full", "selfHash": "uHiD--P_PL077FPKtMajH215ddqst8mO1-dqdjgeZwPRdOQ", "updated": "2025-01-01T00:00:03.875Z", "verified": true, "versionId": "3"}; didResolutionMetadata.fetchedUpdatesFromVDR: expected True, got None; didResolutionMetadata.didDocumentResolvedLocally: expected False, got None; didResolutionMetadata.didDocumentMetadataResolvedLocally: expected True, got None
- **Case repro:** `./run.sh scenarios --resolver zkred --name conflict-via-local-self-hash --catalog-url http://ledgerdomain.github.io/did-webplus-spec/test-vector --timeout 60.0`
- **Suite log:** `logs/scenarios.log` (docker run reproducers are in the tee'd log)

### `scenarios:zkred` — conflicting-query-params

- **Roles:** controller=none, vdr=test-vector-server, vdg=none, resolver=zkred
- **Detail:** didDocumentMetadata mismatch: expected {"updated": "2025-01-01T00:00:03Z", "updatedMilliseconds": "2025-01-01T00:00:03.875Z", "versionId": "3"}, got {"created": "2025-01-01T00:00:00.001Z", "latestVersionId": "3", "mode": "full", "selfHash": "uHiAtY7yTlaqdAG-cxSdVRpDQyPaH8NY8_24M-hjy2dlICg", "updated": "2025-01-01T00:00:03.875Z", "verified": true, "versionId": "3"}; didResolutionMetadata.fetchedUpdatesFromVDR: expected True, got None; didResolutionMetadata.didDocumentResolvedLocally: expected False, got None; didResolutionMetadata.didDocumentMetadataResolvedLocally: expected True, got None
- **Case repro:** `./run.sh scenarios --resolver zkred --name conflicting-query-params --catalog-url http://ledgerdomain.github.io/did-webplus-spec/test-vector --timeout 60.0`
- **Suite log:** `logs/scenarios.log` (docker run reproducers are in the tee'd log)

### `scenarios:zkred` — deactivated-all-local

- **Roles:** controller=none, vdr=test-vector-server, vdg=none, resolver=zkred
- **Detail:** didDocumentMetadata mismatch: expected {"deactivated": true, "updated": "2025-01-01T00:00:03Z", "updatedMilliseconds": "2025-01-01T00:00:03.875Z", "versionId": "3"}, got {"created": "2025-01-01T00:00:00.001Z", "latestVersionId": "3", "mode": "full", "selfHash": "uHiChpeZKxCwBuvsjmkMhwBWJwU43hLiW8cyU98eQrKs13w", "updated": "2025-01-01T00:00:03.875Z", "verified": true, "versionId": "3"}; didResolutionMetadata.fetchedUpdatesFromVDR: expected True, got None; didResolutionMetadata.didDocumentResolvedLocally: expected False, got None; didResolutionMetadata.didDocumentMetadataResolvedLocally: expected True, got None
- **Case repro:** `./run.sh scenarios --resolver zkred --name deactivated-all-local --catalog-url http://ledgerdomain.github.io/did-webplus-spec/test-vector --timeout 60.0`
- **Suite log:** `logs/scenarios.log` (docker run reproducers are in the tee'd log)

### `scenarios:zkred` — deactivated-known-absence

- **Roles:** controller=none, vdr=test-vector-server, vdg=none, resolver=zkred
- **Detail:** didDocumentMetadata mismatch: expected {"deactivated": true, "updated": "2025-01-01T00:00:03Z", "updatedMilliseconds": "2025-01-01T00:00:03.875Z", "versionId": "3"}, got {"created": "2025-01-01T00:00:00.001Z", "latestVersionId": "3", "mode": "full", "selfHash": "uHiDDYsonYG8bvptdscqm1pRLIbblvMXCklJcuFzGUkCmeQ", "updated": "2025-01-01T00:00:03.875Z", "verified": true, "versionId": "3"}; didResolutionMetadata.fetchedUpdatesFromVDR: expected True, got None; didResolutionMetadata.didDocumentResolvedLocally: expected False, got None; didResolutionMetadata.didDocumentMetadataResolvedLocally: expected True, got None
- **Case repro:** `./run.sh scenarios --resolver zkred --name deactivated-known-absence --catalog-url http://ledgerdomain.github.io/did-webplus-spec/test-vector --timeout 60.0`
- **Suite log:** `logs/scenarios.log` (docker run reproducers are in the tee'd log)

### `scenarios:zkred` — fetch-failed-with-local-document

- **Roles:** controller=none, vdr=test-vector-server, vdg=none, resolver=zkred
- **Detail:** didDocumentMetadata mismatch: expected {"updated": "2025-01-01T00:00:03Z", "updatedMilliseconds": "2025-01-01T00:00:03.875Z", "versionId": "3"}, got {"created": "2025-01-01T00:00:00.001Z", "latestVersionId": "3", "mode": "full", "selfHash": "uHiBF4zN-4IlJKdaaMvG1dTsbAuPd9E0sjeFP_7ktIhfUdw", "updated": "2025-01-01T00:00:03.875Z", "verified": true, "versionId": "3"}; didResolutionMetadata.fetchedUpdatesFromVDR: expected True, got None; didResolutionMetadata.didDocumentResolvedLocally: expected False, got None; didResolutionMetadata.didDocumentMetadataResolvedLocally: expected True, got None
- **Case repro:** `./run.sh scenarios --resolver zkred --name fetch-failed-with-local-document --catalog-url http://ledgerdomain.github.io/did-webplus-spec/test-vector --timeout 60.0`
- **Suite log:** `logs/scenarios.log` (docker run reproducers are in the tee'd log)

### `scenarios:zkred` — incremental-range-fetch

- **Roles:** controller=none, vdr=test-vector-server, vdg=none, resolver=zkred
- **Detail:** didDocumentMetadata mismatch: expected {"versionId": "0"}, got {"created": "2025-01-01T00:00:00.001Z", "latestVersionId": "0", "mode": "full", "selfHash": "uHiAT8HhB7HW8-R-OwKgMZ0jUe-g3TiCzNQbdvpetnfVP6w", "updated": "2025-01-01T00:00:00.001Z", "verified": true, "versionId": "0"}; didResolutionMetadata.fetchedUpdatesFromVDR: expected True, got None; didResolutionMetadata.didDocumentResolvedLocally: expected False, got None; didResolutionMetadata.didDocumentMetadataResolvedLocally: expected True, got None
- **Case repro:** `./run.sh scenarios --resolver zkred --name incremental-range-fetch --catalog-url http://ledgerdomain.github.io/did-webplus-spec/test-vector --timeout 60.0`
- **Suite log:** `logs/scenarios.log` (docker run reproducers are in the tee'd log)

### `scenarios:zkred` — local-only-matrix

- **Roles:** controller=none, vdr=test-vector-server, vdg=none, resolver=zkred
- **Detail:** unsupported options: localResolutionOnly; success: expected False, resolution succeeded; expected failure but didResolutionMetadata.error is missing
- **Case repro:** `./run.sh scenarios --resolver zkred --name local-only-matrix --catalog-url http://ledgerdomain.github.io/did-webplus-spec/test-vector --timeout 60.0`
- **Suite log:** `logs/scenarios.log` (docker run reproducers are in the tee'd log)

### `scenarios:zkred` — plain-did-always-fetches

- **Roles:** controller=none, vdr=test-vector-server, vdg=none, resolver=zkred
- **Detail:** didDocumentMetadata mismatch: expected {"updated": "2025-01-01T00:00:03Z", "updatedMilliseconds": "2025-01-01T00:00:03.875Z", "versionId": "3"}, got {"created": "2025-01-01T00:00:00.001Z", "latestVersionId": "3", "mode": "full", "selfHash": "uHiBbG8tKz6-fO5kzpnu7qEeyeEjq6TimadS_CDm4tYoMfA", "updated": "2025-01-01T00:00:03.875Z", "verified": true, "versionId": "3"}; didResolutionMetadata.fetchedUpdatesFromVDR: expected True, got None; didResolutionMetadata.didDocumentResolvedLocally: expected False, got None; didResolutionMetadata.didDocumentMetadataResolvedLocally: expected True, got None
- **Case repro:** `./run.sh scenarios --resolver zkred --name plain-did-always-fetches --catalog-url http://ledgerdomain.github.io/did-webplus-spec/test-vector --timeout 60.0`
- **Suite log:** `logs/scenarios.log` (docker run reproducers are in the tee'd log)

### `scenarios:zkred` — request-creation-cold

- **Roles:** controller=none, vdr=test-vector-server, vdg=none, resolver=zkred
- **Detail:** unsupported options: requestCreate; didDocumentMetadata mismatch: expected {"created": "2025-01-01T00:00:00Z", "createdMilliseconds": "2025-01-01T00:00:00.001Z", "updated": "2025-01-01T00:00:03Z", "updatedMilliseconds": "2025-01-01T00:00:03.875Z", "versionId": "3"}, got {"created": "2025-01-01T00:00:00.001Z", "latestVersionId": "3", "mode": "full", "selfHash": "uHiBFKILcsHMOnH57wsTqfSjREOzhOQWlpA2hXdR0Kb3ZAg", "updated": "2025-01-01T00:00:03.875Z", "verified": true, "versionId": "3"}; didResolutionMetadata.fetchedUpdatesFromVDR: expected True, got None; didResolutionMetadata.didDocumentResolvedLocally: expected False, got None; didResolutionMetadata.didDocumentMetadataResolvedLocally: expected False, got None
- **Case repro:** `./run.sh scenarios --resolver zkred --name request-creation-cold --catalog-url http://ledgerdomain.github.io/did-webplus-spec/test-vector --timeout 60.0`
- **Suite log:** `logs/scenarios.log` (docker run reproducers are in the tee'd log)

### `scenarios:zkred` — request-creation-warm

- **Roles:** controller=none, vdr=test-vector-server, vdg=none, resolver=zkred
- **Detail:** didDocumentMetadata mismatch: expected {"updated": "2025-01-01T00:00:03Z", "updatedMilliseconds": "2025-01-01T00:00:03.875Z", "versionId": "3"}, got {"created": "2025-01-01T00:00:00.001Z", "latestVersionId": "3", "mode": "full", "selfHash": "uHiBjhQyz0cpuB-c_k7gEfRGPwMtolNaGYDIASCIWx0Z2zQ", "updated": "2025-01-01T00:00:03.875Z", "verified": true, "versionId": "3"}; didResolutionMetadata.fetchedUpdatesFromVDR: expected True, got None; didResolutionMetadata.didDocumentResolvedLocally: expected False, got None; didResolutionMetadata.didDocumentMetadataResolvedLocally: expected True, got None
- **Case repro:** `./run.sh scenarios --resolver zkred --name request-creation-warm --catalog-url http://ledgerdomain.github.io/did-webplus-spec/test-vector --timeout 60.0`
- **Suite log:** `logs/scenarios.log` (docker run reproducers are in the tee'd log)

### `scenarios:zkred` — request-deactivated-forces-fetch

- **Roles:** controller=none, vdr=test-vector-server, vdg=none, resolver=zkred
- **Detail:** didDocumentMetadata mismatch: expected {"updated": "2025-01-01T00:00:03Z", "updatedMilliseconds": "2025-01-01T00:00:03.875Z", "versionId": "3"}, got {"created": "2025-01-01T00:00:00.001Z", "latestVersionId": "3", "mode": "full", "selfHash": "uHiAhZR6sehNix5k19HgiOUN1HCt4cPtOs3y_DJVcGK8FPw", "updated": "2025-01-01T00:00:03.875Z", "verified": true, "versionId": "3"}; didResolutionMetadata.fetchedUpdatesFromVDR: expected True, got None; didResolutionMetadata.didDocumentResolvedLocally: expected False, got None; didResolutionMetadata.didDocumentMetadataResolvedLocally: expected True, got None
- **Case repro:** `./run.sh scenarios --resolver zkred --name request-deactivated-forces-fetch --catalog-url http://ledgerdomain.github.io/did-webplus-spec/test-vector --timeout 60.0`
- **Suite log:** `logs/scenarios.log` (docker run reproducers are in the tee'd log)

### `scenarios:zkred` — request-latest-forces-fetch

- **Roles:** controller=none, vdr=test-vector-server, vdg=none, resolver=zkred
- **Detail:** didDocumentMetadata mismatch: expected {"updated": "2025-01-01T00:00:03Z", "updatedMilliseconds": "2025-01-01T00:00:03.875Z", "versionId": "3"}, got {"created": "2025-01-01T00:00:00.001Z", "latestVersionId": "3", "mode": "full", "selfHash": "uHiBo_WJEi99s5efASS5_E0sEysqpqaCEEeRT_Ugdb9QdYA", "updated": "2025-01-01T00:00:03.875Z", "verified": true, "versionId": "3"}; didResolutionMetadata.fetchedUpdatesFromVDR: expected True, got None; didResolutionMetadata.didDocumentResolvedLocally: expected False, got None; didResolutionMetadata.didDocumentMetadataResolvedLocally: expected True, got None
- **Case repro:** `./run.sh scenarios --resolver zkred --name request-latest-forces-fetch --catalog-url http://ledgerdomain.github.io/did-webplus-spec/test-vector --timeout 60.0`
- **Suite log:** `logs/scenarios.log` (docker run reproducers are in the tee'd log)

### `scenarios:zkred` — request-next-at-latest

- **Roles:** controller=none, vdr=test-vector-server, vdg=none, resolver=zkred
- **Detail:** didDocumentMetadata mismatch: expected {"updated": "2025-01-01T00:00:03Z", "updatedMilliseconds": "2025-01-01T00:00:03.875Z", "versionId": "3"}, got {"created": "2025-01-01T00:00:00.001Z", "latestVersionId": "3", "mode": "full", "selfHash": "uHiDyoAqgpXe8spMW2UYMthKv_ojbHrBMSleuRiErla-UpA", "updated": "2025-01-01T00:00:03.875Z", "verified": true, "versionId": "3"}; didResolutionMetadata.fetchedUpdatesFromVDR: expected True, got None; didResolutionMetadata.didDocumentResolvedLocally: expected False, got None; didResolutionMetadata.didDocumentMetadataResolvedLocally: expected True, got None
- **Case repro:** `./run.sh scenarios --resolver zkred --name request-next-at-latest --catalog-url http://ledgerdomain.github.io/did-webplus-spec/test-vector --timeout 60.0`
- **Suite log:** `logs/scenarios.log` (docker run reproducers are in the tee'd log)

### `scenarios:zkred` — request-next-with-local-next

- **Roles:** controller=none, vdr=test-vector-server, vdg=none, resolver=zkred
- **Detail:** didDocumentMetadata mismatch: expected {"updated": "2025-01-01T00:00:03Z", "updatedMilliseconds": "2025-01-01T00:00:03.875Z", "versionId": "3"}, got {"created": "2025-01-01T00:00:00.001Z", "latestVersionId": "3", "mode": "full", "selfHash": "uHiAF0n2Az49xijqcjNNoytaZlXjsI_eQUE2YRxHJiCmJag", "updated": "2025-01-01T00:00:03.875Z", "verified": true, "versionId": "3"}; didResolutionMetadata.fetchedUpdatesFromVDR: expected True, got None; didResolutionMetadata.didDocumentResolvedLocally: expected False, got None; didResolutionMetadata.didDocumentMetadataResolvedLocally: expected True, got None
- **Case repro:** `./run.sh scenarios --resolver zkred --name request-next-with-local-next --catalog-url http://ledgerdomain.github.io/did-webplus-spec/test-vector --timeout 60.0`
- **Suite log:** `logs/scenarios.log` (docker run reproducers are in the tee'd log)

### `scenarios:zkred` — version-beyond-served

- **Roles:** controller=none, vdr=test-vector-server, vdg=none, resolver=zkred
- **Detail:** expected failure but didResolutionMetadata.error is missing
- **Case repro:** `./run.sh scenarios --resolver zkred --name version-beyond-served --catalog-url http://ledgerdomain.github.io/did-webplus-spec/test-vector --timeout 60.0`
- **Suite log:** `logs/scenarios.log` (docker run reproducers are in the tee'd log)

### `scenarios:zkred` — warm-both-params

- **Roles:** controller=none, vdr=test-vector-server, vdg=none, resolver=zkred
- **Detail:** didDocumentMetadata mismatch: expected {"updated": "2025-01-01T00:00:03Z", "updatedMilliseconds": "2025-01-01T00:00:03.875Z", "versionId": "3"}, got {"created": "2025-01-01T00:00:00.001Z", "latestVersionId": "3", "mode": "full", "selfHash": "uHiC37T-TgoY3xR-eM601-r5hv4_nqWFYOJWuaW8suQzSZQ", "updated": "2025-01-01T00:00:03.875Z", "verified": true, "versionId": "3"}; didResolutionMetadata.fetchedUpdatesFromVDR: expected True, got None; didResolutionMetadata.didDocumentResolvedLocally: expected False, got None; didResolutionMetadata.didDocumentMetadataResolvedLocally: expected True, got None
- **Case repro:** `./run.sh scenarios --resolver zkred --name warm-both-params --catalog-url http://ledgerdomain.github.io/did-webplus-spec/test-vector --timeout 60.0`
- **Suite log:** `logs/scenarios.log` (docker run reproducers are in the tee'd log)

### `scenarios:zkred` — warm-self-hash

- **Roles:** controller=none, vdr=test-vector-server, vdg=none, resolver=zkred
- **Detail:** didDocumentMetadata mismatch: expected {"updated": "2025-01-01T00:00:03Z", "updatedMilliseconds": "2025-01-01T00:00:03.875Z", "versionId": "3"}, got {"created": "2025-01-01T00:00:00.001Z", "latestVersionId": "3", "mode": "full", "selfHash": "uHiA-UJsuj75sKJE3QlTm5Ze9JEzDqPqIKlrjYZij3vB55Q", "updated": "2025-01-01T00:00:03.875Z", "verified": true, "versionId": "3"}; didResolutionMetadata.fetchedUpdatesFromVDR: expected True, got None; didResolutionMetadata.didDocumentResolvedLocally: expected False, got None; didResolutionMetadata.didDocumentMetadataResolvedLocally: expected True, got None
- **Case repro:** `./run.sh scenarios --resolver zkred --name warm-self-hash --catalog-url http://ledgerdomain.github.io/did-webplus-spec/test-vector --timeout 60.0`
- **Suite log:** `logs/scenarios.log` (docker run reproducers are in the tee'd log)

### `scenarios:zkred` — warm-version-id

- **Roles:** controller=none, vdr=test-vector-server, vdg=none, resolver=zkred
- **Detail:** didDocumentMetadata mismatch: expected {"updated": "2025-01-01T00:00:03Z", "updatedMilliseconds": "2025-01-01T00:00:03.875Z", "versionId": "3"}, got {"created": "2025-01-01T00:00:00.001Z", "latestVersionId": "3", "mode": "full", "selfHash": "uHiCrjkeINJOXd_RLb0WyZZYtgE4dO6ZphcjnmYNndr6FEQ", "updated": "2025-01-01T00:00:03.875Z", "verified": true, "versionId": "3"}; didResolutionMetadata.fetchedUpdatesFromVDR: expected True, got None; didResolutionMetadata.didDocumentResolvedLocally: expected False, got None; didResolutionMetadata.didDocumentMetadataResolvedLocally: expected True, got None
- **Case repro:** `./run.sh scenarios --resolver zkred --name warm-version-id --catalog-url http://ledgerdomain.github.io/did-webplus-spec/test-vector --timeout 60.0`
- **Suite log:** `logs/scenarios.log` (docker run reproducers are in the tee'd log)

## Logs

- `logs/matrix-01.log`
- `logs/matrix-02.log`
- `logs/matrix-03.log`
- `logs/matrix-04.log`
- `logs/matrix-05.log`
- `logs/matrix-06.log`
- `logs/matrix-07.log`
- `logs/matrix-08.log`
- `logs/matrix-09.log`
- `logs/matrix-10.log`
- `logs/matrix-11.log`
- `logs/matrix-12.log`
- `logs/matrix-13.log`
- `logs/matrix-14.log`
- `logs/matrix-15.log`
- `logs/matrix-16.log`
- `logs/matrix-17.log`
- `logs/matrix-18.log`
- `logs/matrix-19.log`
- `logs/matrix-20.log`
- `logs/matrix-21.log`
- `logs/matrix-22.log`
- `logs/scenarios.log`
- `logs/vectors.log`
