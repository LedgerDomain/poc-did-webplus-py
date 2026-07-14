# `@zkred/did-webplus` version card

**Pinned version: `0.4.0`** (from `package-lock.json` → `packages["node_modules/@zkred/did-webplus"].version`)

Versioning is intentional and manual: a committed lockfile keeps CI/repros stable, while `^0.4.0` in `package.json` allows deliberate bumps via PR. Re-review the package on each lockfile bump (changelog, install scripts, transitive deps). There is no automatic upgrade path.

## Commands

```bash
cd interop

# Check which version will run (lockfile + installed package file)
grep '"@zkred/did-webplus"' package.json package-lock.json
node -e "console.log(JSON.parse(require('fs').readFileSync('node_modules/@zkred/did-webplus/package.json','utf8')).version)"
# Or from the Docker image (override entrypoint; image ENTRYPOINT is ts_runner.mjs):
docker run --rm --entrypoint node did-webplus-zkred -e \
  "console.log(JSON.parse(require('fs').readFileSync('node_modules/@zkred/did-webplus/package.json','utf8')).version)"

# Bump to a new release (then commit package.json + package-lock.json)
npm install @zkred/did-webplus@<version>
# Update the pinned version line at the top of this file in the same PR.

# Rebuild runner image
docker build -f Dockerfile.zkred -t did-webplus-zkred .

# Run TS scenarios
./run_interop_tests.sh 17
./run_all_interop_tests.sh
```

Full operator guide: [README.md § TypeScript implementation](README.md#typescript-implementation-zkreddid-webplus--version-management).
