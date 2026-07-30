# Resolver conformance testing (test-vector catalog)

This suite runs the official did:webplus **test-vector catalog** against the Python, Rust, and Zkred (`@zkred/did-webplus`) resolvers. Each vector’s `test-vector.json` is the oracle: resolve the DID “latest”; accept or reject according to `expected.valid` / `didDocumentCount`.

This is separate from the 22-scenario controller/VDR/resolver interop matrix in [README.md](README.md).

## Prerequisites

- Docker and Docker Compose
- [uv](https://docs.astral.sh/uv/)
- Git submodule initialized (see below)
- `/etc/hosts` entry (same as other interop tests):

```
127.0.0.1  ledgerdomain.github.io
```

> That entry shadows the real GitHub Pages site machine-wide. Comment it out when you need `https://ledgerdomain.github.io` or `scripts/fetch_ledgerdomain_fixtures.py`.

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

What that does: starts only the `ledgerdomain.github.io` compose service, waits for health, streams logs, runs `run_test_vectors.py`, then tears the service down.

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

Zkred runs need the `did-webplus-zkred` image (built on demand via the shared resolver helpers / Docker, same as scenarios 17–22).

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
| `docker-compose.yml` → `ledgerdomain.github.io` | Serves catalog over HTTP (RangeHTTPServer) |
| `run_test_vectors.sh` | Compose lifecycle + runner |
| `run_test_vectors.py` | Fetch index/vectors, run resolvers, report |
| `resolvers.py` | Shared Python / Rust / Zkred resolve helpers |

Root `test-vectors/` (plural) is an older, separate fixture set — not this catalog.
