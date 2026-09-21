# did:webplus Interoperability Testing

Docker-based interoperability tests between the Python implementation, the Rust reference implementation, and the third-party TypeScript library [`@zkred/did-webplus`](https://github.com/Zkred/did-methods/tree/main/packages/did-webplus). Scenarios 1–16 exercise the Python/Rust matrix. Scenarios 17–22 exercise `@zkred/did-webplus` as resolver or controller (see [TypeScript implementation](#typescript-implementation-zkreddid-webplus--version-management)).

## Prerequisites

- Docker and Docker Compose
- Access to the Docker socket (`/var/run/docker.sock`) so the runner containers can start sibling containers for Rust/Zkred
- Node 20+ only if running `ts_runner.mjs` outside Docker (optional; Docker is the primary path)

Relative to previous version of interop test, no `/etc/hosts` edits are required.  If you had edited `/etc/hosts` (in particular, entries for `rust-vdr`, `rust-vdg`, `python-vdr`, and `ledgerdomain.github.io`), then you should remove those entries.  Both the 22-scenario matrix (`interop-runner`) and the test-vector suite (`test-vector-runner`) join the named Docker network `interop-net`; Docker’s embedded DNS resolves `rust-vdr`, `rust-vdg`, `python-vdr`, and `ledgerdomain.github.io` for every container on that network.

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

Each scenario uses a **clean wallet directory** for the duration of the run. The chosen **controller** (Python or Rust CLI, TS/`@zkred/did-webplus` for 21–22, or reference controller for 17–20) performs DID create, DID update, and DID deactivate against the chosen VDR. The chosen **resolver** runs after create (asserts versionId=0), after update (asserts versionId=1), and after deactivate (asserts versionId=2 and deactivated document shape: `updateRules` is `{}`, and `verificationMethod`, `authentication`, `assertionMethod`, `keyAgreement`, `capabilityInvocation`, and `capabilityDelegation` are all `[]`). Scenarios 21–22 use the TS controller for the full lifecycle; both Python and Rust resolvers verify the same DID at each step. When VDG is used, the resolver talks via the Rust VDG and the test asserts VDG headers (e.g. X-DID-Webplus-VDG-Cache-Hit). Create, update, and deactivate are performed only via the controller CLI; Python and Rust controllers require `--confirm THIS-IS-IRREVERSIBLE` for deactivate.

On success, output ends with a parameterized summary, for example:

```
interop INFO === All tests PASSED ===
interop INFO Summary — Scenario 7: Python controller, Rust VDR, Rust resolver, no VDG
interop INFO   Controller created, updated, and deactivated DID; resolver ran after create (v0), update (v1), and deactivate (v2).
```

## Running Tests

Unified entry point: **`./run.sh`** (`matrix` | `vectors` | `scenarios` | `all` | `clean`).

```bash
# From the interop directory
./run.sh matrix              # All 22 controller/VDR/resolver scenarios
./run.sh matrix 1            # Single scenario (1–22)
./run.sh matrix 17           # First TS (@zkred) scenario

./run.sh vectors             # Test-vector resolver conformance (catalog oracle)
./run.sh scenarios           # Resolution-scenario conformance (multi-step + control API)

./run.sh all                 # matrix (all) + vectors + scenarios
./run.sh clean               # Stop compose, remove volumes, reset wallets/
```

Quick TS version card: [`ZKRED_VERSION.md`](ZKRED_VERSION.md).

### Test-vector / resolver conformance suite

The test-vector catalog is the git submodule
`interop/ledgerdomain.github.io/did-webplus-spec`
([LedgerDomain/did-webplus-spec](https://github.com/LedgerDomain/did-webplus-spec)).
This repo pins a specific commit of that submodule.

**Initialize / sync to the pinned commit** — use after a fresh clone (or whenever
you want the working tree to match the SHA recorded in this repo). This does
**not** fetch newer upstream commits; it only checks out the already-recorded pin:

```bash
git submodule update --init interop/ledgerdomain.github.io/did-webplus-spec
```

**Pull newer catalog from upstream** — use when
[did-webplus-spec](https://github.com/LedgerDomain/did-webplus-spec) has moved
ahead and you want those updates locally. `--remote` fetches and checks out the
tracked remote branch tip (typically `main`). The parent repo’s pin does not
change until you stage and commit the new submodule SHA:

```bash
git submodule update --remote interop/ledgerdomain.github.io/did-webplus-spec
git add interop/ledgerdomain.github.io/did-webplus-spec
# commit when ready, after verifying the suite
```

See **[resolver-conformance-testing.md](resolver-conformance-testing.md)** for catalog layout, more submodule detail, the catalog server control API, resolution scenarios, and adapter architecture.

```bash
# After submodule is present (init or update --remote as above)
./run.sh vectors
./run.sh vectors --group positive --resolver python
./run.sh scenarios --resolver rust
```

Resolver implementations are invoked through **`interop/resolvers.py`**: Python (`did-webplus-python-cli` image), Rust (`did-webplus-cli`), and Zkred (`did-webplus-zkred`) as sibling Docker containers on `interop-net`.

## Run reports

Every `./run.sh matrix`, `vectors`, `scenarios`, or `all` invocation writes a timestamped directory under **`interop/reports/`** (gitignored). At the end of the run, `run.sh` prints the path to the rendered summary, for example:

```text
Interop report: interop/reports/2026-09-20T07.11.43Z/report.md
```

`interop/reports/latest` is a symlink to the most recent run.

### Layout

```text
interop/reports/<RUN_ID>/
  run.json              # written at start: argv, env whitelist, host, git, planned units
  suites/*.json         # one artifact per runner (matrix-07, vectors, scenarios, …)
  logs/*.log            # tee'd stdout/stderr per suite
  report.json           # aggregate (schemaVersion); written at end by report.py
  report.md             # human-readable summary from report.json
```

`RUN_ID` is UTC time (`YYYY-MM-DDTHH.MM.SSZ`). If the process dies before `report.json` exists, `run.json` and whatever landed in `suites/` still show how far the run got.

`./run.sh clean` stops compose, removes volumes, and resets `wallets/`; it does **not** delete `reports/`.

### Verdicts

Verdicts are **per unit only** — one matrix scenario, or one resolver within one catalog suite (`vectors` / `scenarios`). They are not rolled up per component across categories.

| Verdict | Meaning |
|---------|---------|
| **PASS** | Every case that should run for that unit ran and passed. |
| **FAIL** | A case failed, or a planned case did not run (`not-run`). |

`report.md` lists verdict rows with pass/expected counts, duration, and copy-paste repro commands (including env prefixes when non-default options were set). Each row includes **Controller**, **VDR**, **VDG**, and **Resolver** columns with normalized implementation names (`python`, `rust`, `zkred`, `test-vector-server`, or `none`). Catalog suites use `test-vector-server` as the VDR; matrix scenarios use `none` for VDG when that axis is off. Failures include assertion detail, the failing matrix step name when applicable, and per-case repro lines; full `docker run` lines from the resolver harness are in the tee'd suite logs linked from the report.

To regenerate `report.json` / `report.md` from an existing directory (for example after pulling report.py fixes):

```bash
python3 interop/report.py interop/reports/<RUN_ID>
```

## TypeScript implementation (`@zkred/did-webplus`) — version management

Third-party library from [Zkred/did-methods](https://github.com/Zkred/did-methods/tree/main/packages/did-webplus) (`@zkred/did-webplus` on npm). Interop scenarios 17–22 invoke it via `ts_runner.mjs` inside the `did-webplus-zkred` Docker image.

| What | Where |
|------|-------|
| Pinned version | `interop/package-lock.json` → `packages["node_modules/@zkred/did-webplus"].version` |
| Allowed range | `interop/package.json` → `"@zkred/did-webplus": "^X.Y.Z"` |
| Override for one-off runs | `INTEROP_ZKRED_DID_WEBPLUS_VERSION` env var |
| Runner image | Built from `interop/Dockerfile.zkred`; `./run.sh` rebuilds when lockfile or override changes |
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

1. Edit `interop/package.json` if the semver range needs widening.
2. Run `npm update @zkred/did-webplus` (or `npm install @zkred/did-webplus@<version>`) inside `interop/`.
3. Commit **both** `package.json` and `package-lock.json`. Update the pinned version line in [`ZKRED_VERSION.md`](ZKRED_VERSION.md).
4. **Re-review** the new version before merging: skim [Zkred/did-methods CHANGELOG](https://github.com/Zkred/did-methods/blob/main/packages/did-webplus/CHANGELOG.md), confirm no new install scripts, check transitive deps in the lockfile diff.
5. Run TS scenarios to verify: `./run.sh matrix 17` then `./run.sh matrix` (rebuilds the zkred image automatically).

### Test a specific version without committing

To specify a specific version `X.Y.Z`, use

```bash
INTEROP_ZKRED_DID_WEBPLUS_VERSION=X.Y.Z ./run.sh matrix 17
```

Or a git ref:

```bash
INTEROP_ZKRED_DID_WEBPLUS_VERSION='github:Zkred/did-methods#abc1234' ./run.sh matrix 17
```

Overrides rebuild the image for that run only and do **not** modify `package-lock.json`.

> **Image rebuild:** `./run.sh` rebuilds `did-webplus-zkred` automatically before matrix, vectors, or scenarios when `package.json`, `package-lock.json`, or `INTEROP_ZKRED_DID_WEBPLUS_VERSION` changes (`Dockerfile.zkred` copies the lockfiles before `npm ci`, so a lockfile bump invalidates the layer). No manual `docker build` is required.

### Scenarios 17–22 (TS roles)

| # | TS role | Controller | VDR | Resolver under test | VDG | Lifecycle tested |
|---|---------|------------|-----|---------------------|-----|------------------|
| 17 | Resolver | Python | Python | **TS** | no | Full (create → v0 → update → v1 → deactivate → v2) |
| 18 | Resolver | Python | Python | **TS** | yes | Full + VDG header checks |
| 19 | Resolver | Rust | Rust | **TS** | no | Full |
| 20 | Resolver | Rust | Rust | **TS** | yes | Full + VDG header checks |
| 21 | Controller | **TS** | Python | Python **and** Rust (same scenario) | no | Full (create → v0 → update → v1 → deactivate → v2) |
| 22 | Controller | **TS** | Rust | Python **and** Rust (same scenario) | no | Full (create → v0 → update → v1 → deactivate → v2) |

**Prerequisites for local (non-Docker) TS runs:** Node 20+. Primary path is Docker (`did-webplus-zkred`); set `INTEROP_ZKRED_LOCAL=1` only for local `node ts_runner.mjs` development.

Attribution: [`@zkred/did-webplus`](https://github.com/Zkred/did-methods/tree/main/packages/did-webplus) by Zkred ([did-methods](https://github.com/Zkred/did-methods)).

## Cleanup

To stop all containers and remove volumes (guaranteed clean slate):

```bash
./run.sh clean
```

## Docker Images

- **Rust VDR**: `ghcr.io/ledgerdomain/did-webplus-vdr`
- **Rust VDG**: `ghcr.io/ledgerdomain/did-webplus-vdg`
- **Rust CLI** (`ghcr.io/ledgerdomain/did-webplus-cli`): used as **DID resolver** when Resolver=Rust and as **DID controller** when Controller=Rust (wallet in Docker volume).
- **Python VDR**: Built from this repo (`interop/Dockerfile.python-vdr`)
- **Python resolver** (`did-webplus-python-cli`): built from `interop/Dockerfile.python-cli`; sibling container for catalog suites (matrix controller still uses in-runner `did-webplus` CLI today).
- **Python controller**: This repo’s `did-webplus did create` / `did update` / `did deactivate` (deactivate requires `--confirm THIS-IS-IRREVERSIBLE`); uses a local wallet directory (created per run).
- **Zkred TS runner** (`did-webplus-zkred`): built from `interop/Dockerfile.zkred`; bundles `@zkred/did-webplus` at the lockfile-pinned version. **Version management instructions: see [TypeScript implementation](#typescript-implementation-zkreddid-webplus--version-management).**

## Ports

- Rust VDR: 8085
- Rust VDG: 8086
- Python VDR: 8087
- Test-vector catalog server (`ledgerdomain.github.io`, static + control API): 80

## Reproducibility

The interoperability tests can be replicated on a fresh Ubuntu 24.04 instance, assuming username `ubuntu`, as follows.  Note that it seemed like 512MB of memory wasn't sufficient, but 1024MB of memory was sufficient.

    sudo apt update
    sudo apt install --yes docker.io docker-compose-v2
    sudo usermod -aG docker ubuntu

Log out and back in to have usermod take effect.

    cd ~ && git clone https://github.com/LedgerDomain/poc-did-webplus-py.git
    cd ~/poc-did-webplus-py
    # Checkout the catalog commit pinned by this repo (not latest upstream)
    git submodule update --init interop/ledgerdomain.github.io/did-webplus-spec
    cd interop
    ./run.sh matrix

`./run.sh matrix` runs all 22 scenarios. No `/etc/hosts` edits are needed — service hostnames resolve via Docker network DNS (`interop-net`). Scenarios 17–22 require building the zkred runner image (`did-webplus-zkred`); that build happens automatically. The TS package version is determined by the committed `interop/package-lock.json` at clone time (unless you set `INTEROP_ZKRED_DID_WEBPLUS_VERSION` for a one-off override). See [TypeScript implementation](#typescript-implementation-zkreddid-webplus--version-management) and [`ZKRED_VERSION.md`](ZKRED_VERSION.md).

To refresh the catalog beyond the pin recorded in this repo, use
`git submodule update --remote …` (see [Test-vector / resolver conformance suite](#test-vector--resolver-conformance-suite)), then commit the new submodule SHA if you intend to keep it.
