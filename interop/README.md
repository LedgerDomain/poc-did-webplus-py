# did:webplus Interoperability Testing

Docker-based interoperability tests between the Python implementation and the Rust reference implementation. Each scenario combines a **DID controller** (Python or Rust), a **VDR** (Python or Rust), a **DID resolver** (Python or Rust), and whether the **Rust VDG** sits in front of the VDR.

## Prerequisites

- Docker and Docker Compose
- [uv](https://docs.astral.sh/uv/) (for running the test script)

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

16 scenarios from 4 binary axes: **Controller** (Python/Rust), **VDR** (Python/Rust), **Resolver** (Python/Rust), **VDG** (no/yes).

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

### Test Details

Each scenario uses a **clean wallet directory** for the duration of the run. The chosen **controller** (Python or Rust CLI) performs DID create, DID update, and DID deactivate against the chosen VDR. The chosen **resolver** runs after create (asserts versionId=0), after update (asserts versionId=1), and after deactivate (asserts versionId=2 and deactivated document shape: `updateRules` is `{}`, and `verificationMethod`, `authentication`, `assertionMethod`, `keyAgreement`, `capabilityInvocation`, and `capabilityDelegation` are all `[]`). When VDG is used, the resolver talks via the Rust VDG and the test asserts VDG headers (e.g. X-DID-Webplus-VDG-Cache-Hit). Create, update, and deactivate are performed only via the controller CLI; both Python and Rust controllers require `--confirm THIS-IS-IRREVERSIBLE` for deactivate.

On success, output ends with a parameterized summary, for example:

```
interop INFO === All tests PASSED ===
interop INFO Summary — Scenario 7: Python controller, Rust VDR, Rust resolver, no VDG
interop INFO   Controller created, updated, and deactivated DID; resolver ran after create (v0), update (v1), and deactivate (v2).
```

## Running Tests

```bash
# From the interop directory
./run_all_interop_tests.sh   # Run all 16 scenarios

# Or run a single scenario (1-16):
./run_interop_tests.sh 1
./run_interop_tests.sh 10
```

## Cleanup

To stop all containers and remove volumes (guaranteed clean slate):

```bash
./stop_and_clean.sh
```

## Docker Images

- **Rust VDR**: `ghcr.io/ledgerdomain/did-webplus-vdr:v0.1.0`
- **Rust VDG**: `ghcr.io/ledgerdomain/did-webplus-vdg:v0.1.0`
- **Rust CLI** (`ghcr.io/ledgerdomain/did-webplus-cli:v0.1.1`): used as **DID resolver** when Resolver=Rust and as **DID controller** when Controller=Rust (wallet in Docker volume).
- **Python VDR**: Built from this repo (`interop/Dockerfile.python-vdr`)
- **Python controller**: This repo’s `did-webplus did create` / `did update` / `did deactivate` (deactivate requires `--confirm THIS-IS-IRREVERSIBLE`); uses a local wallet directory (created per run).

## Ports

- Rust VDR: 8085
- Rust VDG: 8086
- Python VDR: 8087
