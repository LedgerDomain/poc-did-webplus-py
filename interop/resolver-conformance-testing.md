# Resolver conformance testing (test-vector catalog)

This suite runs the official did:webplus **test-vector catalog** against the Python, Rust, and Zkred (`@zkred/did-webplus`) resolvers. Each vector’s `test-vector.json` is the oracle: resolve the DID “latest”; accept or reject according to `expected.valid` / `didDocumentCount`.

This is separate from the 22-scenario controller/VDR/resolver interop matrix in [README.md](README.md).

## Prerequisites

- Docker and Docker Compose
- Git submodule initialized (see below)
- Access to the Docker socket (`/var/run/docker.sock`) so the runner can start sibling containers for the Rust and Zkred resolvers

Relative to previous version of interop test, no `/etc/hosts` edits are required.  If you had edited `/etc/hosts` (in particular, entries for `rust-vdr`, `rust-vdg`, `python-vdr`, and `ledgerdomain.github.io`), then you should remove those entries.  The `ledgerdomain.github.io` compose service and the `test-vector-runner` both join the named Docker network `interop-net`; Docker’s embedded DNS resolves that hostname for every container on the network. Rust/Zkred sibling `docker run` calls use `--network interop-net` via `DID_WEBPLUS_INTEROP_DOCKER_NETWORK` (set by compose).

## Test-vector catalog (git submodule)

Catalog source: [LedgerDomain/did-webplus-spec](https://github.com/LedgerDomain/did-webplus-spec), directory `test-vector/`.

Pinned in this repo as a **git submodule** at:

```
interop/ledgerdomain.github.io/did-webplus-spec/
```

Compose mounts `…/test-vector` into a static Range-capable HTTP server named `ledgerdomain.github.io`, so resolution URLs match the DIDs in the catalog (`did:webplus:ledgerdomain.github.io:did-webplus-spec:test-vector:…` on port 80).

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

```bash
cd interop
./run_test_vectors.sh
```

What that does: starts the `ledgerdomain.github.io` compose service, waits for health, streams logs, builds the zkred image when needed, then `docker compose run --rm --build test-vector-runner` (which runs `run_test_vectors.py` inside the runner container on `interop-net`), and tears the service down.

The `test-vector-runner` image bundles `uv` + `did_webplus` and the Docker CLI. It mounts `/var/run/docker.sock` so Rust/Zkred resolves spawn as sibling containers on `interop-net` (same Docker daemon), while the Python resolver runs in-process inside the runner.

### Useful filters

```bash
./run_test_vectors.sh --resolver python
./run_test_vectors.sh --resolver rust
./run_test_vectors.sh --resolver zkred
./run_test_vectors.sh --group positive --resolver python
./run_test_vectors.sh --name baseline-valid-root --resolver all
./run_test_vectors.sh --jobs 4 --timeout 120
```

`--group` and `--name` are repeatable. Default `--resolver` is `all` (python + rust + zkred).

Zkred runs need the `did-webplus-zkred` image (built on demand by `run_test_vectors.sh` / the shared resolver helpers, same as scenarios 17–22).

## Oracle (what “pass” means)

For each selected vector and resolver:

| Condition | Expected |
|-----------|----------|
| `didDocumentCount == 0` | Resolve must **fail** |
| `expected.valid == true` | Resolve must **succeed**; resolved `versionId` must equal `didDocumentCount - 1` |
| `expected.valid == false` | Resolve must **fail** |

`errorCode` / `errorVersionId` in the vector are advisory only (logged in failure detail, not asserted).

## Layout / pointers

| Piece | Role |
|-------|------|
| Submodule `…/did-webplus-spec` | Pinned catalog + `test-vector/index.json` |
| `docker-compose.yml` → `ledgerdomain.github.io` | Serves catalog over HTTP (RangeHTTPServer on port 80) on `interop-net` |
| `docker-compose.yml` → `test-vector-runner` | Orchestrator container (`uv` + Docker CLI; socket mount for sibling Rust/Zkred) |
| `run_test_vectors.sh` | Compose lifecycle + `compose run test-vector-runner` |
| `run_test_vectors.py` | Fetch index/vectors, run resolvers, report |
| `resolvers.py` | Shared Python / Rust / Zkred resolve helpers (`DID_WEBPLUS_INTEROP_DOCKER_NETWORK`) |

Root `test-vectors/` (plural) is an older, separate fixture set — not this catalog.
