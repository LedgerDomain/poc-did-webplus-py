# Resolver conformance testing (test-vector catalog)

This suite runs the official did:webplus **test-vector catalog** against the Python, Rust, and Zkred (`@zkred/did-webplus`) resolvers. Each vector’s `test-vector.json` is the oracle: resolve the DID “latest”; accept or reject according to `expected.valid` / `didDocumentCount`.

A separate **resolution-scenario** group in the same catalog exercises multi-step resolution (serve-count truncation, request counters, resolution options, persistent doc store). See [Resolution scenarios](#resolution-scenarios) below.

This is separate from the 22-scenario controller/VDR/resolver interop matrix in [README.md](README.md).

## Prerequisites

- Docker and Docker Compose
- Git submodule initialized (see below)
- Access to the Docker socket (`/var/run/docker.sock`) so the runner can start sibling containers for Rust, Zkred, and the Python CLI resolver

Relative to previous version of interop test, no `/etc/hosts` edits are required. The `ledgerdomain.github.io` compose service and the `test-vector-runner` both join the named Docker network `interop-net`; Docker’s embedded DNS resolves service hostnames for every container on the network. Sibling `docker run` calls use `--network interop-net` via `DID_WEBPLUS_INTEROP_DOCKER_NETWORK` (set by compose).

## Test-vector catalog (git submodule)

Catalog source: [LedgerDomain/did-webplus-spec](https://github.com/LedgerDomain/did-webplus-spec), directory `test-vector/`.

Pinned in this repo as a **git submodule** at:

```
interop/ledgerdomain.github.io/did-webplus-spec/
```

Compose mounts `…/test-vector` into the catalog HTTP server named `ledgerdomain.github.io`, so resolution URLs match the DIDs in the catalog (`did:webplus:ledgerdomain.github.io:did-webplus-spec:test-vector:…` on port 80).

### Clone / init

```bash
# Fresh clone
git clone --recurse-submodules https://github.com/LedgerDomain/poc-did-webplus-py.git

# Or if you already cloned without submodules
git submodule update --init interop/ledgerdomain.github.io/did-webplus-spec
```

### See the pinned commit

```bash
git submodule status interop/ledgerdomain.github.io/did-webplus-spec
# or
git -C interop/ledgerdomain.github.io/did-webplus-spec rev-parse HEAD
```

### Pull a newer catalog (bump the pin)

```bash
cd interop/ledgerdomain.github.io/did-webplus-spec
git fetch origin
git checkout origin/main          # or a specific SHA
cd ../../..
git add interop/ledgerdomain.github.io/did-webplus-spec
git status   # should show submodule pointer changed
# commit when ready
```

Or from the repo root:

```bash
git submodule update --remote interop/ledgerdomain.github.io/did-webplus-spec
git add interop/ledgerdomain.github.io/did-webplus-spec
```

Then run the suite and commit the new submodule SHA if results look good.

## How to run

All catalog suites use the unified entry point:

```bash
cd interop
./run.sh vectors          # test-vector group (parallel per vector)
./run.sh scenarios        # resolution-scenario group (sequential per step)
./run.sh clean            # tear down compose + wallet dirs
```

What `./run.sh vectors` or `./run.sh scenarios` does: build resolver images (`did-webplus-python-cli`, `did-webplus-zkred`), start the `ledgerdomain.github.io` compose service, wait for health, stream logs, then `docker compose run --rm --build test-vector-runner` with the appropriate Python module on `interop-net`, and tear the service down on exit.

The `test-vector-runner` image bundles `uv` + `did_webplus` and the Docker CLI. It mounts `/var/run/docker.sock` so Python, Rust, and Zkred resolvers spawn as sibling containers on `interop-net` (same Docker daemon).

### Useful filters

```bash
./run.sh vectors --resolver python
./run.sh vectors --resolver rust
./run.sh vectors --resolver zkred
./run.sh vectors --group positive --resolver python
./run.sh vectors --name baseline-valid-root --resolver all
./run.sh vectors --jobs 4 --timeout 120

./run.sh scenarios --resolver python
./run.sh scenarios --name some-scenario-name
```

`--group` and `--name` are repeatable. Default `--resolver` is `all` (python + rust + zkred).

Zkred runs need the `did-webplus-zkred` image (built on demand by `./run.sh`, same as matrix scenarios 17–22).

## Catalog server (static + control API)

`interop/test_vector_server.py` serves the mounted catalog tree and implements:

| Endpoint | Purpose |
|----------|---------|
| `GET /health` | JSON `{"ok": true, "controlApi": true, …}` — compose healthcheck and `./run.sh` preflight (detects stale static-only images) |
| Static files under `did-webplus-spec/test-vector/` | `index.json`, vectors, `did-documents.jsonl` |
| `PUT /control/serve-count` | Truncate served `did-documents.jsonl` to first N lines (per vector `path`) |
| `GET /control/request-count?path=…` | Count GETs of that vector’s `did-documents.jsonl` |
| `POST /control/reset` | Reset all serve-counts (full file) and request counters |

HTTP **Range** requests are honored against the *effective* (truncated) body length so incremental fetches behave like a live VDR. With default serve-count (all lines), the server is a drop-in for the old static Range server used by `./run.sh vectors`.

**Sequential execution:** scenario steps call `POST /control/reset` before each step because counters and serve-count state are global per server instance. Do not run two scenario jobs against the same catalog server concurrently.

## Oracle — test-vector group

For each selected vector and resolver:

| Condition | Expected |
|-----------|----------|
| `didDocumentCount == 0` | Resolve must **fail** |
| `expected.valid == true` | Resolve must **succeed**; resolved `versionId` must equal `didDocumentCount - 1` |
| `expected.valid == false` | Resolve must **fail** |

`errorCode` / `errorVersionId` in the vector are advisory only (logged in failure detail, not asserted).

## Resolution scenarios

Vectors in index group `resolution-scenario` ship `resolution-scenario.json` (format `did-webplus-resolution-scenario/1`). For each scenario the runner:

1. Creates a fresh persistent doc-store directory (kept across steps within the scenario).
2. For each step: reset control state, set `servedDidDocumentCount`, resolve `didQuery` with `resolutionOptions`, assert normative expectations, assert `vdrRequestCount` matches the server counter.

**Normative assertions:**

- Resolve success or failure as specified
- On success: `didDocumentVersionId`, `didDocumentSelfHash`, exact `didDocumentMetadata` JSON equality
- Resolution metadata booleans: `fetchedUpdatesFromVDR`, `didDocumentResolvedLocally`, `didDocumentMetadataResolvedLocally`
- On failure: `didResolutionMetadata.error` present

`contentType` and error message text are advisory (logged only). Range fetch behavior beyond `vdrRequestCount` is not asserted.

## Resolver adapters

`interop/resolvers.py` exposes a single `resolve(did_query, *, options, store_dir, vdg_url, timeout) -> ResolveResult` used by the matrix runner, test vectors, and resolution scenarios. Wire `resolutionOptions` map to per-implementation CLI flags; unsupported options are recorded on the result for reporting.

| Resolver | Image / invocation |
|----------|-------------------|
| Python | `did-webplus-python-cli` sibling container (`resolve … -o json --base-dir <store>`) |
| Rust | Pinned `ghcr.io/ledgerdomain/did-webplus-cli` with doc-store mount and `-C/-N/-L/-D/-l` flags |
| Zkred | `did-webplus-zkred` → `ts_runner.mjs resolve` |

## Layout / pointers

| Piece | Role |
|-------|------|
| Submodule `…/did-webplus-spec` | Pinned catalog + `test-vector/index.json` |
| `docker-compose.yml` → `ledgerdomain.github.io` | Catalog server on port 80 (`interop-net`) |
| `docker-compose.yml` → `test-vector-runner` | Orchestrator container (`uv` + Docker CLI) |
| `./run.sh` | Compose lifecycle for vectors, scenarios, matrix, clean |
| `run_test_vectors.py` | Fetch index/vectors, run resolvers, report |
| `run_resolution_scenarios.py` | Sequential scenario steps + control API |
| `resolvers.py` | Shared resolver adapters |

Root `test-vectors/` (plural) is an older, separate fixture set — not this catalog.
