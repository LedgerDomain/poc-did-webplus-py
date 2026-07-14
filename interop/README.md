# did:webplus Interoperability Testing

Docker-based interoperability tests between the Python implementation, the Rust reference implementation, and the third-party TypeScript library [`@zkred/did-webplus`](https://github.com/Zkred/did-methods/tree/main/packages/did-webplus). Scenarios 1–16 exercise the Python/Rust matrix. Scenarios 17–22 exercise `@zkred/did-webplus` as resolver or controller (see [TypeScript implementation](#typescript-implementation-zkreddid-webplus--version-management)).

## Prerequisites

- Docker and Docker Compose
- [uv](https://docs.astral.sh/uv/) (for running the test script)
- Node 20+ only if running `ts_runner.mjs` outside Docker (optional; Docker is the primary path)

## Hostname Setup

The interop tests use hostnames `rust-vdr`, `rust-vdg`, and `python-vdr` for HTTP requests. Add these entries to your system's `/etc/hosts` so they resolve to localhost:

```
# Used for poc-did-webplus-py interop testing
127.0.0.1  rust-vdr
127.0.0.1  rust-vdg
127.0.0.1  python-vdr
```

On Linux/macOS, edit `/etc/hosts` with sudo (e.g. `sudo nano /etc/hosts`) and add the lines above.

## Test Matrix

**Scenarios 1–16:** 4 binary axes — **Controller** (Python/Rust), **VDR** (Python/Rust), **Resolver** (Python/Rust), **VDG** (no/yes).

| # | Controller | VDR | Resolver | VDG |
|---|------------|-----|----------|-----|
| 1 | Python | Python | Python | no |
| 2 | Python | Python | Python | yes |
| 3 | Python | Python | Rust | no |
| 4 | Python | Python | Rust | yes |
| 5 | Python | Rust | Python | no |
| 6 | Python | Rust | Python | yes |
| 7 | Python | Rust | Rust | no |
| 8 | Python | Rust | Rust | yes |
| 9 | Rust | Python | Python | no |
| 10 | Rust | Python | Python | yes |
| 11 | Rust | Python | Rust | no |
| 12 | Rust | Python | Rust | yes |
| 13 | Rust | Rust | Python | no |
| 14 | Rust | Rust | Python | yes |
| 15 | Rust | Rust | Rust | no |
| 16 | Rust | Rust | Rust | yes |

**Scenarios 17–22:** TypeScript (`@zkred/did-webplus`) role-targeted coverage. See the full table under [TypeScript implementation](#typescript-implementation-zkreddid-webplus--version-management).

### Test Details

Each scenario uses a **clean wallet directory** for the duration of the run. For scenarios 1–20, the chosen **controller** (Python or Rust CLI, or reference controller for 17–20) performs DID create, DID update, and DID deactivate against the chosen VDR. The chosen **resolver** runs after create (asserts versionId=0), after update (asserts versionId=1), and after deactivate (asserts versionId=2 and deactivated document shape: `updateRules` is `{}`, and `verificationMethod`, `authentication`, `assertionMethod`, `keyAgreement`, `capabilityInvocation`, and `capabilityDelegation` are all `[]`). When VDG is used, the resolver talks via the Rust VDG and the test asserts VDG headers (e.g. X-DID-Webplus-VDG-Cache-Hit). Create, update, and deactivate are performed only via the controller CLI; both Python and Rust controllers require `--confirm THIS-IS-IRREVERSIBLE` for deactivate.

Scenarios 21–22 use the TS controller for create + update only (no deactivate until the library supports it); both Python and Rust resolvers verify the same DID.

On success, output ends with a parameterized summary, for example:

```
interop INFO === All tests PASSED ===
interop INFO Summary — Scenario 7: Python controller, Rust VDR, Rust resolver, no VDG
interop INFO   Controller created, updated, and deactivated DID; resolver ran after create (v0), update (v1), and deactivate (v2).
```

## Running Tests

```bash
# From the interop directory
./run_all_interop_tests.sh   # Run all 22 scenarios

# Or run a single scenario (1-22):
./run_interop_tests.sh 1
./run_interop_tests.sh 10
./run_interop_tests.sh 17   # first TS scenario
```

Quick TS version card: [`ZKRED_VERSION.md`](ZKRED_VERSION.md).

## TypeScript implementation (`@zkred/did-webplus`) — version management

Third-party library from [Zkred/did-methods](https://github.com/Zkred/did-methods/tree/main/packages/did-webplus) (`@zkred/did-webplus` on npm). Interop scenarios 17–22 invoke it via `ts_runner.mjs` inside the `did-webplus-zkred` Docker image. TS controller scenarios intentionally omit deactivate until the library exports a deactivate helper.

| What | Where |
|------|-------|
| Pinned version | `interop/package-lock.json` → `packages["node_modules/@zkred/did-webplus"].version` (currently **0.4.0**) |
| Allowed range | `interop/package.json` → `"@zkred/did-webplus": "^0.4.0"` |
| Override for one-off runs | `INTEROP_ZKRED_DID_WEBPLUS_VERSION` env var |
| Runner image | Built from `interop/Dockerfile.zkred` (rebuild required after version change) |
| Scenarios affected | 17–22 only (1–16 unchanged) |

### Check which version will run

```bash
cd interop

# Declared range + lockfile pin
grep '"@zkred/did-webplus"' package.json package-lock.json

# Version actually installed under node_modules (host; after npm ci)
# Note: require('@zkred/did-webplus/package.json') fails — the package "exports"
# map does not expose ./package.json. Read the file from disk instead:
node -e "console.log(JSON.parse(require('fs').readFileSync('node_modules/@zkred/did-webplus/package.json','utf8')).version)"

# Version baked into the Docker image (override ENTRYPOINT; default is ts_runner.mjs)
docker run --rm --entrypoint node did-webplus-zkred -e \
  "console.log(JSON.parse(require('fs').readFileSync('node_modules/@zkred/did-webplus/package.json','utf8')).version)"
```

### Bump to a new release (standard workflow)

1. Edit `interop/package.json` if the semver range needs widening (e.g. `^0.5.0`).
2. Run `npm update @zkred/did-webplus` (or `npm install @zkred/did-webplus@<version>`) inside `interop/`.
3. Commit **both** `package.json` and `package-lock.json`. Update the pinned version line in [`ZKRED_VERSION.md`](ZKRED_VERSION.md).
4. **Re-review** the new version before merging: skim [Zkred/did-methods CHANGELOG](https://github.com/Zkred/did-methods/blob/main/packages/did-webplus/CHANGELOG.md), confirm no new install scripts, check transitive deps in the lockfile diff.
5. Rebuild the zkred Docker image: `docker build -f Dockerfile.zkred -t did-webplus-zkred .`
6. Run TS scenarios to verify: `./run_interop_tests.sh 17` then `./run_all_interop_tests.sh`.

### Test a specific version without committing

```bash
INTEROP_ZKRED_DID_WEBPLUS_VERSION=0.4.1 ./run_interop_tests.sh 17
# or a git ref:
INTEROP_ZKRED_DID_WEBPLUS_VERSION='github:Zkred/did-methods#abc1234' ./run_interop_tests.sh 17
```

Overrides rebuild the image for that run only and do **not** modify `package-lock.json`.

> **When rebuild is required:** After any change to `package.json`, `package-lock.json`, or `INTEROP_ZKRED_DID_WEBPLUS_VERSION`, the zkred runner image must be rebuilt. `run_interop_tests.sh` does this automatically for scenarios 17–22 (and builds the image unconditionally for simplicity).

### Scenarios 17–22 (TS roles)

| # | TS role | Controller | VDR | Resolver under test | VDG | Lifecycle tested |
|---|---------|------------|-----|---------------------|-----|------------------|
| 17 | Resolver | Python | Python | **TS** | no | Full (create → v0 → update → v1 → deactivate → v2) |
| 18 | Resolver | Python | Python | **TS** | yes | Full + VDG header checks |
| 19 | Resolver | Rust | Rust | **TS** | no | Full |
| 20 | Resolver | Rust | Rust | **TS** | yes | Full + VDG header checks |
| 21 | Controller | **TS** | Python | Python **and** Rust (same scenario) | no | Create + update only (v0, v1) |
| 22 | Controller | **TS** | Rust | Python **and** Rust (same scenario) | no | Create + update only (v0, v1) |

**Prerequisites for local (non-Docker) TS runs:** Node 20+. Primary path is Docker (`did-webplus-zkred`); set `INTEROP_ZKRED_LOCAL=1` only for local `node ts_runner.mjs` development.

Attribution: [`@zkred/did-webplus`](https://github.com/Zkred/did-methods/tree/main/packages/did-webplus) by Zkred ([did-methods](https://github.com/Zkred/did-methods)).

## Cleanup

To stop all containers and remove volumes (guaranteed clean slate):

```bash
./stop_and_clean.sh
```

## Docker Images

- **Rust VDR**: `ghcr.io/ledgerdomain/did-webplus-vdr:v0.1.0`
- **Rust VDG**: `ghcr.io/ledgerdomain/did-webplus-vdg:v0.1.0`
- **Rust CLI** (`ghcr.io/ledgerdomain/did-webplus-cli:v0.1.2`): used as **DID resolver** when Resolver=Rust and as **DID controller** when Controller=Rust (wallet in Docker volume).
- **Python VDR**: Built from this repo (`interop/Dockerfile.python-vdr`)
- **Python controller**: This repo’s `did-webplus did create` / `did update` / `did deactivate` (deactivate requires `--confirm THIS-IS-IRREVERSIBLE`); uses a local wallet directory (created per run).
- **Zkred TS runner** (`did-webplus-zkred`): built from `interop/Dockerfile.zkred`; bundles `@zkred/did-webplus` at the lockfile-pinned version. **Version management instructions: see [TypeScript implementation](#typescript-implementation-zkreddid-webplus--version-management).**

## Ports

- Rust VDR: 8085
- Rust VDG: 8086
- Python VDR: 8087

## Reproducibility

The interoperability tests can be replicated on a fresh Ubuntu 24.04 instance, assuming username `ubuntu`, as follows.  Note that it seemed like 512MB of memory wasn't sufficient, but 1024MB of memory was sufficient.

    sudo apt update
    sudo apt install --yes docker.io docker-compose-v2
    curl -LsSf https://astral.sh/uv/install.sh | sh
    sudo usermod -aG docker ubuntu

Log out and back in to have usermod take effect.

    sudo vim /etc/hosts

And add:

    # Used for poc-did-webplus-py interop testing
    127.0.0.1  rust-vdr
    127.0.0.1  rust-vdg
    127.0.0.1  python-vdr

Then:

    cd ~ && git clone https://github.com/LedgerDomain/poc-did-webplus-py.git
    cd ~/poc-did-webplus-py/interop
    ./run_all_interop_tests.sh

`./run_all_interop_tests.sh` runs all 22 scenarios. Scenarios 17–22 require building the zkred runner image (`did-webplus-zkred`); that build happens automatically in the shell scripts. The TS package version is determined by the committed `interop/package-lock.json` at clone time (unless you set `INTEROP_ZKRED_DID_WEBPLUS_VERSION` for a one-off override). See [TypeScript implementation](#typescript-implementation-zkreddid-webplus--version-management) and [`ZKRED_VERSION.md`](ZKRED_VERSION.md).
