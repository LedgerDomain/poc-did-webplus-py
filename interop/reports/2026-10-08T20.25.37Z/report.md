# Interop run report

## Header

- **Run ID:** `2026-10-08T20.25.37Z`
- **Generated:** 2026-10-08T20:38:56Z
- **Started:** 2026-10-08T20:25:37Z
- **Ended:** 2026-10-08T20:38:56Z
- **Duration:** 799.0s
- **Invocation:** `./run.sh all`
- **Test repo git commit hash:** `743e2b6f48888ff07ad40050e65d21f22287a96a` on `main` (dirty)
- **Catalog submodule:** `4099496d96bb758cff25d9fc95e074d245ed37e2`
- **Host:** x86_64 / Linux 7.0.0-34-generic; cpus=22; docker=Docker version 29.1.3, build 29.1.3-0ubuntu3~24.04.2; compose=Docker Compose version 2.40.3+ds1-0ubuntu1~24.04.1

## Verdicts

| Unit | Controller | VDR | VDG | Resolver | Verdict | Passed | Expected | Duration | Repro |
|------|------------|-----|-----|----------|---------|--------|----------|----------|-------|
| `matrix:1` | python | python | none | python | PASS | 1 | 1 | 8.6s | `./run.sh matrix 1` |
| `matrix:2` | python | python | rust | python | PASS | 1 | 1 | 9.7s | `./run.sh matrix 2` |
| `matrix:3` | python | python | none | rust | PASS | 1 | 1 | 10.0s | `./run.sh matrix 3` |
| `matrix:4` | python | python | rust | rust | PASS | 1 | 1 | 6.7s | `./run.sh matrix 4` |
| `matrix:5` | python | rust | none | python | PASS | 1 | 1 | 8.7s | `./run.sh matrix 5` |
| `matrix:6` | python | rust | rust | python | PASS | 1 | 1 | 10.2s | `./run.sh matrix 6` |
| `matrix:7` | python | rust | none | rust | PASS | 1 | 1 | 5.3s | `./run.sh matrix 7` |
| `matrix:8` | python | rust | rust | rust | PASS | 1 | 1 | 6.7s | `./run.sh matrix 8` |
| `matrix:9` | rust | python | none | python | PASS | 1 | 1 | 8.4s | `./run.sh matrix 9` |
| `matrix:10` | rust | python | rust | python | PASS | 1 | 1 | 10.0s | `./run.sh matrix 10` |
| `matrix:11` | rust | python | none | rust | PASS | 1 | 1 | 4.8s | `./run.sh matrix 11` |
| `matrix:12` | rust | python | rust | rust | PASS | 1 | 1 | 6.1s | `./run.sh matrix 12` |
| `matrix:13` | rust | rust | none | python | PASS | 1 | 1 | 9.1s | `./run.sh matrix 13` |
| `matrix:14` | rust | rust | rust | python | PASS | 1 | 1 | 9.7s | `./run.sh matrix 14` |
| `matrix:15` | rust | rust | none | rust | PASS | 1 | 1 | 4.8s | `./run.sh matrix 15` |
| `matrix:16` | rust | rust | rust | rust | PASS | 1 | 1 | 6.2s | `./run.sh matrix 16` |
| `matrix:17` | python | python | none | zkred | PASS | 1 | 1 | 6.0s | `./run.sh matrix 17` |
| `matrix:18` | python | python | rust | zkred | PASS | 1 | 1 | 7.7s | `./run.sh matrix 18` |
| `matrix:19` | rust | rust | none | zkred | PASS | 1 | 1 | 5.5s | `./run.sh matrix 19` |
| `matrix:20` | rust | rust | rust | zkred | PASS | 1 | 1 | 6.7s | `./run.sh matrix 20` |
| `matrix:21` | zkred | python | none | python, rust | PASS | 1 | 1 | 9.2s | `./run.sh matrix 21` |
| `matrix:22` | zkred | rust | none | python, rust | PASS | 1 | 1 | 9.6s | `./run.sh matrix 22` |
| `vectors:python` | none | test-vector-server | none | python | PASS | 302 | 302 | 86.8s | `./run.sh vectors --resolver python` |
| `vectors:rust` | none | test-vector-server | none | rust | PASS | 302 | 302 | 22.0s | `./run.sh vectors --resolver rust` |
| `vectors:zkred` | none | test-vector-server | none | zkred | PASS | 302 | 302 | 37.6s | `./run.sh vectors --resolver zkred` |
| `scenarios:python` | none | test-vector-server | none | python | PASS | 19 | 19 | 60.2s | `./run.sh scenarios --resolver python` |
| `scenarios:rust` | none | test-vector-server | none | rust | PASS | 19 | 19 | 11.9s | `./run.sh scenarios --resolver rust` |
| `scenarios:zkred` | none | test-vector-server | none | zkred | FAIL | 10 | 19 | 17.1s | `./run.sh scenarios --resolver zkred` |

## Invoked components

- **controller/python:** did-webplus-python-cli — image ID `sha256:59cf80b2ab2cfd6ab57946fda4bd92e2a37e9e9a9a7e9218b1f8c608a66a6a32` (from this repo)
- **controller/rust:** ghcr.io/ledgerdomain/did-webplus-cli:v0.7.0 — image ID `sha256:81f566bfbb24d0bef822cd13d61941abad21895e75c6c9fddf45a3533ea30e2e`
- **controller/zkred:** did-webplus-zkred — image ID `sha256:f297b272d6dcd7d1d0bea136a979385f1286176c0ae173637fa3e798bc2dbc5a` (from this repo, zkred pin `1.0.1`)
- **resolver/python:** did-webplus-python-cli — image ID `sha256:59cf80b2ab2cfd6ab57946fda4bd92e2a37e9e9a9a7e9218b1f8c608a66a6a32` (from this repo)
- **resolver/rust:** ghcr.io/ledgerdomain/did-webplus-cli:v0.7.0 — image ID `sha256:81f566bfbb24d0bef822cd13d61941abad21895e75c6c9fddf45a3533ea30e2e`
- **resolver/zkred:** did-webplus-zkred — image ID `sha256:f297b272d6dcd7d1d0bea136a979385f1286176c0ae173637fa3e798bc2dbc5a` (from this repo, zkred pin `1.0.1`)
- **vdg/rust:** ghcr.io/ledgerdomain/did-webplus-vdg:v0.6.0 — image ID `sha256:d86a35e97202ccd225469c1ec64a4d3ecb16dce6bb4a238a50f42ce17e9c5fa4`
- **vdr/python:** interop-python-vdr — image ID `sha256:02a0419660d5496377a3976cb4f6afb2276844a7f6d54bad968967ae1ce4cae2` (from this repo)
- **vdr/rust:** ghcr.io/ledgerdomain/did-webplus-vdr:v0.6.0 — image ID `sha256:907b3b46b7afcca74d569e67670d17b2f026e689678f70a07dec012dda70badd`
- **vdr/test-vector-server:** Built for interop testing; serves the test-vector catalog at ledgerdomain.github.io/did-webplus-spec/test-vector — image ID `sha256:e20ac991342d919691f94229a26acb730cd85d014759ab3629e8a4f489f98a1b` (catalog submodule `4099496d96bb758cff25d9fc95e074d245ed37e2`)

## Failures

### `scenarios:zkred` — deactivated-all-local

- **Roles:** controller=none, vdr=test-vector-server, vdg=none, resolver=zkred
- **Step:** 1
- **Detail:** unsupported options: requestCreate, requestNext, requestLatest, requestDeactivated, localResolutionOnly; didDocumentMetadata mismatch: expected {"created": "2025-01-01T00:00:00Z", "createdMilliseconds": "2025-01-01T00:00:00.001Z", "deactivated": true, "latestUpdate": "2025-01-01T00:00:03Z", "latestUpdateMilliseconds": "2025-01-01T00:00:03.875Z", "latestVersionId": "3", "updated": "2025-01-01T00:00:03Z", "updatedMilliseconds": "2025-01-01T00:00:03.875Z", "versionId": "3"}, got {"deactivated": true, "updated": "2025-01-01T00:00:03Z", "updatedMilliseconds": "2025-01-01T00:00:03.875Z", "versionId": "3"}
- **Case repro:** `./run.sh scenarios --resolver zkred --name deactivated-all-local --catalog-url http://ledgerdomain.github.io/did-webplus-spec/test-vector --timeout 60.0`
- **Suite log:** `logs/scenarios.log` (docker run reproducers are in the tee'd log)

### `scenarios:zkred` — fetch-failed-with-local-document

- **Roles:** controller=none, vdr=test-vector-server, vdg=none, resolver=zkred
- **Step:** 1
- **Detail:** unsupported options: requestLatest; success: expected False, resolution succeeded; expected failure but didResolutionMetadata.error is missing
- **Case repro:** `./run.sh scenarios --resolver zkred --name fetch-failed-with-local-document --catalog-url http://ledgerdomain.github.io/did-webplus-spec/test-vector --timeout 60.0`
- **Suite log:** `logs/scenarios.log` (docker run reproducers are in the tee'd log)

### `scenarios:zkred` — local-only-matrix

- **Roles:** controller=none, vdr=test-vector-server, vdg=none, resolver=zkred
- **Detail:** unsupported options: localResolutionOnly; success: expected False, resolution succeeded; expected failure but didResolutionMetadata.error is missing
- **Case repro:** `./run.sh scenarios --resolver zkred --name local-only-matrix --catalog-url http://ledgerdomain.github.io/did-webplus-spec/test-vector --timeout 60.0`
- **Suite log:** `logs/scenarios.log` (docker run reproducers are in the tee'd log)

### `scenarios:zkred` — request-creation-cold

- **Roles:** controller=none, vdr=test-vector-server, vdg=none, resolver=zkred
- **Detail:** unsupported options: requestCreate; didDocumentMetadata mismatch: expected {"created": "2025-01-01T00:00:00Z", "createdMilliseconds": "2025-01-01T00:00:00.001Z", "updated": "2025-01-01T00:00:03Z", "updatedMilliseconds": "2025-01-01T00:00:03.875Z", "versionId": "3"}, got {"updated": "2025-01-01T00:00:03Z", "updatedMilliseconds": "2025-01-01T00:00:03.875Z", "versionId": "3"}; didResolutionMetadata.didDocumentMetadataResolvedLocally: expected False, got True
- **Case repro:** `./run.sh scenarios --resolver zkred --name request-creation-cold --catalog-url http://ledgerdomain.github.io/did-webplus-spec/test-vector --timeout 60.0`
- **Suite log:** `logs/scenarios.log` (docker run reproducers are in the tee'd log)

### `scenarios:zkred` — request-creation-warm

- **Roles:** controller=none, vdr=test-vector-server, vdg=none, resolver=zkred
- **Step:** 1
- **Detail:** unsupported options: requestCreate; didDocumentMetadata mismatch: expected {"created": "2025-01-01T00:00:00Z", "createdMilliseconds": "2025-01-01T00:00:00.001Z", "updated": "2025-01-01T00:00:02Z", "updatedMilliseconds": "2025-01-01T00:00:02.242Z", "versionId": "2"}, got {"updated": "2025-01-01T00:00:02Z", "updatedMilliseconds": "2025-01-01T00:00:02.242Z", "versionId": "2"}
- **Case repro:** `./run.sh scenarios --resolver zkred --name request-creation-warm --catalog-url http://ledgerdomain.github.io/did-webplus-spec/test-vector --timeout 60.0`
- **Suite log:** `logs/scenarios.log` (docker run reproducers are in the tee'd log)

### `scenarios:zkred` — request-deactivated-forces-fetch

- **Roles:** controller=none, vdr=test-vector-server, vdg=none, resolver=zkred
- **Step:** 1
- **Detail:** unsupported options: requestDeactivated; didDocumentMetadata mismatch: expected {"deactivated": false, "versionId": "0"}, got {"versionId": "0"}; didResolutionMetadata.fetchedUpdatesFromVDR: expected True, got False; didResolutionMetadata.didDocumentMetadataResolvedLocally: expected False, got True
- **Case repro:** `./run.sh scenarios --resolver zkred --name request-deactivated-forces-fetch --catalog-url http://ledgerdomain.github.io/did-webplus-spec/test-vector --timeout 60.0`
- **Suite log:** `logs/scenarios.log` (docker run reproducers are in the tee'd log)

### `scenarios:zkred` — request-latest-forces-fetch

- **Roles:** controller=none, vdr=test-vector-server, vdg=none, resolver=zkred
- **Step:** 1
- **Detail:** unsupported options: requestLatest; didDocumentMetadata mismatch: expected {"latestUpdate": "2025-01-01T00:00:03Z", "latestUpdateMilliseconds": "2025-01-01T00:00:03.875Z", "latestVersionId": "3", "updated": "2025-01-01T00:00:01Z", "updatedMilliseconds": "2025-01-01T00:00:01.633Z", "versionId": "1"}, got {"updated": "2025-01-01T00:00:01Z", "updatedMilliseconds": "2025-01-01T00:00:01.633Z", "versionId": "1"}; didResolutionMetadata.fetchedUpdatesFromVDR: expected True, got False; didResolutionMetadata.didDocumentMetadataResolvedLocally: expected False, got True
- **Case repro:** `./run.sh scenarios --resolver zkred --name request-latest-forces-fetch --catalog-url http://ledgerdomain.github.io/did-webplus-spec/test-vector --timeout 60.0`
- **Suite log:** `logs/scenarios.log` (docker run reproducers are in the tee'd log)

### `scenarios:zkred` — request-next-at-latest

- **Roles:** controller=none, vdr=test-vector-server, vdg=none, resolver=zkred
- **Step:** 1
- **Detail:** unsupported options: requestNext; didResolutionMetadata.fetchedUpdatesFromVDR: expected True, got False; didResolutionMetadata.didDocumentMetadataResolvedLocally: expected False, got True
- **Case repro:** `./run.sh scenarios --resolver zkred --name request-next-at-latest --catalog-url http://ledgerdomain.github.io/did-webplus-spec/test-vector --timeout 60.0`
- **Suite log:** `logs/scenarios.log` (docker run reproducers are in the tee'd log)

### `scenarios:zkred` — request-next-with-local-next

- **Roles:** controller=none, vdr=test-vector-server, vdg=none, resolver=zkred
- **Step:** 1
- **Detail:** unsupported options: requestNext; didDocumentMetadata mismatch: expected {"nextUpdate": "2025-01-01T00:00:02Z", "nextUpdateMilliseconds": "2025-01-01T00:00:02.242Z", "nextVersionId": "2", "updated": "2025-01-01T00:00:01Z", "updatedMilliseconds": "2025-01-01T00:00:01.633Z", "versionId": "1"}, got {"updated": "2025-01-01T00:00:01Z", "updatedMilliseconds": "2025-01-01T00:00:01.633Z", "versionId": "1"}
- **Case repro:** `./run.sh scenarios --resolver zkred --name request-next-with-local-next --catalog-url http://ledgerdomain.github.io/did-webplus-spec/test-vector --timeout 60.0`
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
