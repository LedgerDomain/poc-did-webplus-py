# Interop run report

## Header

- **Run ID:** `2026-10-29T21.44.00Z`
- **Generated:** 2026-10-29T21:56:30Z
- **Started:** 2026-10-29T21:44:00Z
- **Ended:** 2026-10-29T21:56:30Z
- **Duration:** 750.0s
- **Invocation:** `./run.sh all`
- **Test repo git commit hash:** `83b6ae0e3dcb3729f6673dbcb2859588bbddfcbf` on `zkred-options-and-macos` (dirty)
- **Catalog submodule:** `4099496d96bb758cff25d9fc95e074d245ed37e2`
- **Host:** x86_64 / Linux 7.0.0-42-generic; cpus=22; docker=Docker version 29.1.3, build 29.1.3-0ubuntu3~24.04.2; compose=Docker Compose version 2.40.3+ds1-0ubuntu1~24.04.1

## Verdicts

| Unit | Controller | VDR | VDG | Resolver | Verdict | Passed | Expected | Duration | Repro |
|------|------------|-----|-----|----------|---------|--------|----------|----------|-------|
| `matrix:1` | python | python | none | python | PASS | 1 | 1 | 7.9s | `./run.sh matrix 1` |
| `matrix:2` | python | python | rust | python | PASS | 1 | 1 | 10.3s | `./run.sh matrix 2` |
| `matrix:3` | python | python | none | rust | PASS | 1 | 1 | 5.0s | `./run.sh matrix 3` |
| `matrix:4` | python | python | rust | rust | PASS | 1 | 1 | 6.5s | `./run.sh matrix 4` |
| `matrix:5` | python | rust | none | python | PASS | 1 | 1 | 8.1s | `./run.sh matrix 5` |
| `matrix:6` | python | rust | rust | python | PASS | 1 | 1 | 9.3s | `./run.sh matrix 6` |
| `matrix:7` | python | rust | none | rust | PASS | 1 | 1 | 5.1s | `./run.sh matrix 7` |
| `matrix:8` | python | rust | rust | rust | PASS | 1 | 1 | 6.4s | `./run.sh matrix 8` |
| `matrix:9` | rust | python | none | python | PASS | 1 | 1 | 7.6s | `./run.sh matrix 9` |
| `matrix:10` | rust | python | rust | python | PASS | 1 | 1 | 9.0s | `./run.sh matrix 10` |
| `matrix:11` | rust | python | none | rust | PASS | 1 | 1 | 4.5s | `./run.sh matrix 11` |
| `matrix:12` | rust | python | rust | rust | PASS | 1 | 1 | 6.1s | `./run.sh matrix 12` |
| `matrix:13` | rust | rust | none | python | PASS | 1 | 1 | 7.5s | `./run.sh matrix 13` |
| `matrix:14` | rust | rust | rust | python | PASS | 1 | 1 | 8.8s | `./run.sh matrix 14` |
| `matrix:15` | rust | rust | none | rust | PASS | 1 | 1 | 4.6s | `./run.sh matrix 15` |
| `matrix:16` | rust | rust | rust | rust | PASS | 1 | 1 | 6.0s | `./run.sh matrix 16` |
| `matrix:17` | python | python | none | zkred | PASS | 1 | 1 | 5.6s | `./run.sh matrix 17` |
| `matrix:18` | python | python | rust | zkred | PASS | 1 | 1 | 6.9s | `./run.sh matrix 18` |
| `matrix:19` | rust | rust | none | zkred | PASS | 1 | 1 | 5.1s | `./run.sh matrix 19` |
| `matrix:20` | rust | rust | rust | zkred | PASS | 1 | 1 | 6.4s | `./run.sh matrix 20` |
| `matrix:21` | zkred | python | none | python, rust | PASS | 1 | 1 | 8.7s | `./run.sh matrix 21` |
| `matrix:22` | zkred | rust | none | python, rust | PASS | 1 | 1 | 8.8s | `./run.sh matrix 22` |
| `vectors:python` | none | test-vector-server | none | python | PASS | 302 | 302 | 68.1s | `./run.sh vectors --resolver python` |
| `vectors:rust` | none | test-vector-server | none | rust | PASS | 302 | 302 | 20.9s | `./run.sh vectors --resolver rust` |
| `vectors:zkred` | none | test-vector-server | none | zkred | PASS | 302 | 302 | 31.8s | `./run.sh vectors --resolver zkred` |
| `scenarios:python` | none | test-vector-server | none | python | PASS | 19 | 19 | 48.9s | `./run.sh scenarios --resolver python` |
| `scenarios:rust` | none | test-vector-server | none | rust | PASS | 19 | 19 | 11.2s | `./run.sh scenarios --resolver rust` |
| `scenarios:zkred` | none | test-vector-server | none | zkred | PASS | 19 | 19 | 16.6s | `./run.sh scenarios --resolver zkred` |

## Invoked components

- **controller/python:** did-webplus-python-cli — image ID `sha256:5ca70f4c5a89a6cb1a24d9a1b2010cbfc1b16c9e94cd241abd876eb6cbc49907` (from this repo)
- **controller/rust:** ghcr.io/ledgerdomain/did-webplus-cli:v0.7.0 — image ID `sha256:81f566bfbb24d0bef822cd13d61941abad21895e75c6c9fddf45a3533ea30e2e`
- **controller/zkred:** did-webplus-zkred — image ID `sha256:3a163befa89d3a75781d496b22f93855b8459536a1cc7887c88c131c72bb9c41` (from this repo, zkred pin `1.0.1`)
- **resolver/python:** did-webplus-python-cli — image ID `sha256:5ca70f4c5a89a6cb1a24d9a1b2010cbfc1b16c9e94cd241abd876eb6cbc49907` (from this repo)
- **resolver/rust:** ghcr.io/ledgerdomain/did-webplus-cli:v0.7.0 — image ID `sha256:81f566bfbb24d0bef822cd13d61941abad21895e75c6c9fddf45a3533ea30e2e`
- **resolver/zkred:** did-webplus-zkred — image ID `sha256:3a163befa89d3a75781d496b22f93855b8459536a1cc7887c88c131c72bb9c41` (from this repo, zkred pin `1.0.1`)
- **vdg/rust:** ghcr.io/ledgerdomain/did-webplus-vdg:v0.6.0 — image ID `sha256:d86a35e97202ccd225469c1ec64a4d3ecb16dce6bb4a238a50f42ce17e9c5fa4`
- **vdr/python:** interop-python-vdr — image ID `sha256:a8acf100b9ab985ae2743aa0c6e01f0b5b3dd183c5d180c160efcb942a412370` (from this repo)
- **vdr/rust:** ghcr.io/ledgerdomain/did-webplus-vdr:v0.6.0 — image ID `sha256:907b3b46b7afcca74d569e67670d17b2f026e689678f70a07dec012dda70badd`
- **vdr/test-vector-server:** Built for interop testing; serves the test-vector catalog at ledgerdomain.github.io/did-webplus-spec/test-vector — image ID `sha256:e20ac991342d919691f94229a26acb730cd85d014759ab3629e8a4f489f98a1b` (catalog submodule `4099496d96bb758cff25d9fc95e074d245ed37e2`)

## Failures

_None._
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
