#!/usr/bin/env node
/**
 * CLI runner for @zkred/did-webplus interop (scenarios 17–22).
 *
 * Commands:
 *   node ts_runner.mjs controller create  --vdr-url <url> --wallet-dir <dir>
 *   node ts_runner.mjs controller update  --did <base-did> --wallet-dir <dir>
 *   node ts_runner.mjs resolve <did> [--vdg-url <url>] -o json
 */
import { mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { join } from "node:path";
import {
  createDidDocument,
  ed25519KeyPair,
  hashedKeyRule,
  registerDid,
  resolve,
  submitDidUpdate,
  updateDidDocument,
} from "@zkred/did-webplus";

const STATE_FILENAME = "zkred_state.json";
const HTTP_SCHEME = { scheme: "http" };

function usage() {
  return `Usage:
  node ts_runner.mjs controller create  --vdr-url <url> --wallet-dir <dir>
  node ts_runner.mjs controller update  --did <base-did> --wallet-dir <dir>
  node ts_runner.mjs resolve <did> [--vdg-url <url>] -o json`;
}

function fail(message, code = 1) {
  console.error(message);
  process.exit(code);
}

function bytesToB64(bytes) {
  return Buffer.from(bytes).toString("base64");
}

function b64ToBytes(b64) {
  return new Uint8Array(Buffer.from(b64, "base64"));
}

function serializeKey(keyPair) {
  return {
    curve: keyPair.curve,
    privateKeyB64: bytesToB64(keyPair.privateKey),
  };
}

function deserializeKey(stored) {
  if (!stored || stored.curve !== "ed25519" || typeof stored.privateKeyB64 !== "string") {
    throw new Error("wallet state key must be ed25519 with privateKeyB64");
  }
  return ed25519KeyPair(b64ToBytes(stored.privateKeyB64));
}

function statePath(walletDir) {
  return join(walletDir, STATE_FILENAME);
}

function loadState(walletDir) {
  const path = statePath(walletDir);
  let raw;
  try {
    raw = readFileSync(path, "utf8");
  } catch (err) {
    throw new Error(`failed to read wallet state at ${path}: ${err.message}`);
  }
  const state = JSON.parse(raw);
  if (!state.document || !state.signingKey || !state.updateKey) {
    throw new Error(`invalid wallet state at ${path}: need signingKey, updateKey, document`);
  }
  return state;
}

function saveState(walletDir, state) {
  mkdirSync(walletDir, { recursive: true });
  writeFileSync(statePath(walletDir), `${JSON.stringify(state, null, 2)}\n`);
}

/** Parse VDR create URL into createDidDocument host/port/path. */
function parseVdrUrl(vdrUrl) {
  let url;
  try {
    url = new URL(vdrUrl);
  } catch {
    throw new Error(`invalid --vdr-url: ${vdrUrl}`);
  }
  if (url.protocol !== "http:" && url.protocol !== "https:") {
    throw new Error(`--vdr-url scheme must be http or https: ${vdrUrl}`);
  }
  const host = url.hostname;
  if (!host) {
    throw new Error(`--vdr-url missing hostname: ${vdrUrl}`);
  }
  const port = url.port ? Number(url.port) : undefined;
  if (port !== undefined && (!Number.isInteger(port) || port < 1 || port > 65535)) {
    throw new Error(`--vdr-url has invalid port: ${vdrUrl}`);
  }
  const path = url.pathname
    .split("/")
    .map((s) => s.trim())
    .filter(Boolean);
  return { host, port, path };
}

function takeFlagValue(args, i, flag) {
  const value = args[i + 1];
  if (value === undefined || value.startsWith("-")) {
    fail(`missing value for ${flag}\n${usage()}`);
  }
  return value;
}

function parseArgv(argv) {
  if (argv.length === 0) {
    fail(usage());
  }
  if (argv[0] === "controller") {
    const sub = argv[1];
    if (sub !== "create" && sub !== "update") {
      fail(`unknown controller subcommand: ${sub ?? "(missing)"}\n${usage()}`);
    }
    const rest = argv.slice(2);
    const out = { command: "controller", subcommand: sub, vdrUrl: null, did: null, walletDir: null };
    for (let i = 0; i < rest.length; i++) {
      const a = rest[i];
      if (a === "--vdr-url") {
        out.vdrUrl = takeFlagValue(rest, i, a);
        i++;
      } else if (a === "--did") {
        out.did = takeFlagValue(rest, i, a);
        i++;
      } else if (a === "--wallet-dir") {
        out.walletDir = takeFlagValue(rest, i, a);
        i++;
      } else {
        fail(`unknown argument: ${a}\n${usage()}`);
      }
    }
    if (!out.walletDir) {
      fail(`--wallet-dir is required\n${usage()}`);
    }
    if (sub === "create" && !out.vdrUrl) {
      fail(`--vdr-url is required for controller create\n${usage()}`);
    }
    if (sub === "update" && !out.did) {
      fail(`--did is required for controller update\n${usage()}`);
    }
    return out;
  }
  if (argv[0] === "resolve") {
    const rest = argv.slice(1);
    const out = { command: "resolve", did: null, vdgUrl: null, output: null };
    for (let i = 0; i < rest.length; i++) {
      const a = rest[i];
      if (a === "--vdg-url") {
        out.vdgUrl = takeFlagValue(rest, i, a);
        i++;
      } else if (a === "-o" || a === "--output") {
        out.output = takeFlagValue(rest, i, a);
        i++;
      } else if (a.startsWith("-")) {
        fail(`unknown argument: ${a}\n${usage()}`);
      } else if (out.did === null) {
        out.did = a;
      } else {
        fail(`unexpected argument: ${a}\n${usage()}`);
      }
    }
    if (!out.did) {
      fail(`resolve requires a DID\n${usage()}`);
    }
    if (out.output !== "json") {
      fail(`resolve requires -o json\n${usage()}`);
    }
    return out;
  }
  fail(`unknown command: ${argv[0]}\n${usage()}`);
}

async function controllerCreate({ vdrUrl, walletDir }) {
  const { host, port, path } = parseVdrUrl(vdrUrl);
  const signingKey = ed25519KeyPair();
  const updateKey = ed25519KeyPair();
  const doc = createDidDocument({
    host,
    ...(port !== undefined ? { port } : {}),
    ...(path.length > 0 ? { path } : {}),
    keys: [{ publicKey: signingKey.publicKey }],
    updateRules: hashedKeyRule(updateKey.publicKey),
  });
  await registerDid(doc, HTTP_SCHEME);
  saveState(walletDir, {
    signingKey: serializeKey(signingKey),
    updateKey: serializeKey(updateKey),
    document: doc,
  });
  // Base DID (no query); harness strips query if present.
  console.log(doc.id);
}

async function controllerUpdate({ did, walletDir }) {
  const state = loadState(walletDir);
  const baseDid = did.split("?")[0];
  if (state.document.id !== baseDid) {
    throw new Error(
      `wallet document id ${state.document.id} does not match --did ${baseDid}`,
    );
  }
  const updateKey = deserializeKey(state.updateKey);
  const nextSigningKey = ed25519KeyPair();
  const nextUpdateKey = ed25519KeyPair();
  const doc = updateDidDocument(state.document, {
    keys: [{ publicKey: nextSigningKey.publicKey }],
    updateRules: hashedKeyRule(nextUpdateKey.publicKey),
    signers: [updateKey],
  });
  await submitDidUpdate(doc, HTTP_SCHEME);
  saveState(walletDir, {
    signingKey: serializeKey(nextSigningKey),
    updateKey: serializeKey(nextUpdateKey),
    document: doc,
  });
}

/**
 * Normalize TS resolve() output to match Python/Rust CLI JSON shape used by
 * the interop harness: didDocument as a JSON string, not an object.
 */
function normalizeResolveResult(result) {
  const didDocument =
    result.didDocument == null
      ? null
      : typeof result.didDocument === "string"
        ? result.didDocument
        : JSON.stringify(result.didDocument);
  return {
    didDocument,
    didDocumentMetadata: result.didDocumentMetadata ?? {},
  };
}

async function resolveDid({ did, vdgUrl }) {
  const options = {
    ...HTTP_SCHEME,
    verify: true,
  };
  if (vdgUrl) {
    options.vdg = vdgUrl;
  }
  const result = await resolve(did, options);
  const normalized = normalizeResolveResult(result);
  if (result.didResolutionMetadata?.error || !normalized.didDocument) {
    console.error(JSON.stringify({ ...normalized, didResolutionMetadata: result.didResolutionMetadata }, null, 2));
    process.exit(1);
  }
  console.log(JSON.stringify(normalized));
}

async function main() {
  const parsed = parseArgv(process.argv.slice(2));
  try {
    if (parsed.command === "controller" && parsed.subcommand === "create") {
      await controllerCreate(parsed);
      return;
    }
    if (parsed.command === "controller" && parsed.subcommand === "update") {
      await controllerUpdate(parsed);
      return;
    }
    if (parsed.command === "resolve") {
      await resolveDid(parsed);
      return;
    }
    fail(usage());
  } catch (err) {
    fail(err instanceof Error ? err.stack || err.message : String(err));
  }
}

await main();
