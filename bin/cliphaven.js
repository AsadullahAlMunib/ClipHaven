#!/usr/bin/env node
"use strict";

const fs = require("fs");
const os = require("os");
const path = require("path");
const https = require("https");
const crypto = require("crypto");
const readline = require("readline");
const { spawn, spawnSync } = require("child_process");

const PKG_ROOT = path.resolve(__dirname, "..");
const pkg = JSON.parse(fs.readFileSync(path.join(PKG_ROOT, "package.json"), "utf8"));
const VERSION = pkg.version || "3.3.1";
const REPO = "AsadullahAlMunib/ClipHaven";
const HOME_DATA_DIR = path.join(os.homedir(), ".cliphaven");

function printHelp() {
  console.log(`ClipHaven v${VERSION} — Local-only Video & Audio Downloader
Usage:
  npx @asadullahalmunib/cliphaven [url] [options]
  cliphaven [url] [options]

Options:
  -p, --port <port>   Bind local server to a specific port (default: 8765)
      --no-browser    Start server without opening the browser automatically
  -u, --update        Update yt-dlp/Python engine (or refresh cached binary)
      --doctor        Check Node, Python, venv, FFmpeg, aria2c & binary cache
      --force-binary  Skip Python check and run the prebuilt GitHub Release binary
      --no-update-check Skip checking for new ClipHaven CLI releases
  -v, --version       Show ClipHaven version
  -h, --help          Show this help message`);
}

function parseArgs(argv) {
  const opts = { port: "", noBrowser: false, forceBinary: false, noUpdateCheck: false, doctor: false, update: false, url: "", version: false, help: false };
  for (let i = 0; i < argv.length; i++) {
    const arg = argv[i];
    if (arg === "-h" || arg === "--help") {
      opts.help = true;
    } else if (arg === "-v" || arg === "--version") {
      opts.version = true;
    } else if (arg === "-u" || arg === "--update") {
      opts.update = true;
    } else if (arg === "--no-browser") {
      opts.noBrowser = true;
    } else if (arg === "--force-binary") {
      opts.forceBinary = true;
    } else if (arg === "--no-update-check") {
      opts.noUpdateCheck = true;
    } else if (arg === "--doctor") {
      opts.doctor = true;
    } else if (arg === "-p" || arg === "--port") {
      opts.port = String(argv[++i] || "").trim();
    } else if (arg.startsWith("--port=")) {
      opts.port = arg.slice("--port=".length).trim();
    } else if (!arg.startsWith("-") && /^https?:\/\//i.test(arg.trim()) && !opts.url) {
      opts.url = arg.trim();
    }
  }
  return opts;
}

function findPython310() {
  const candidates = process.platform === "win32"
    ? [["py", ["-3"]], ["python", []], ["python3", []]]
    : [["python3", []], ["python", []]];

  for (const [cmd, prefix] of candidates) {
    try {
      const res = spawnSync(
        cmd,
        [...prefix, "-c", "import sys; print(f'{sys.version_info[0]}.{sys.version_info[1]}'); sys.exit(0 if sys.version_info >= (3, 10) else 1)"],
        { encoding: "utf8", timeout: 5000, stdio: ["ignore", "pipe", "ignore"] }
      );
      if (res.status === 0) {
        return { cmd, prefix, version: (res.stdout || "").trim() };
      }
    } catch (_) {}
  }
  return null;
}

function ensurePythonVenv(pyInfo, forceUpgrade = false) {
  const venvDir = path.join(HOME_DATA_DIR, "venv");
  const venvPython = process.platform === "win32"
    ? path.join(venvDir, "Scripts", "python.exe")
    : path.join(venvDir, "bin", "python");

  fs.mkdirSync(HOME_DATA_DIR, { recursive: true });

  if (!fs.existsSync(venvPython)) {
    console.log(`[ClipHaven] Setting up isolated Python environment (${pyInfo.version}) in ${venvDir}…`);
    const mk = spawnSync(pyInfo.cmd, [...pyInfo.prefix, "-m", "venv", venvDir], { stdio: "inherit" });
    if (mk.status !== 0 || !fs.existsSync(venvPython)) {
      return null;
    }
  }

  const reqFile = path.join(PKG_ROOT, "requirements.txt");
  const reqHashFile = path.join(venvDir, ".req_hash");
  const reqContent = fs.existsSync(reqFile) ? fs.readFileSync(reqFile, "utf8") : "";
  const wantHash = crypto.createHash("sha256").update(reqContent).digest("hex");
  const haveHash = fs.existsSync(reqHashFile) ? fs.readFileSync(reqHashFile, "utf8").trim() : "";

  if (forceUpgrade || wantHash !== haveHash) {
    console.log(
      forceUpgrade
        ? "[ClipHaven] Upgrading yt-dlp, imageio-ffmpeg, and mutagen…"
        : "[ClipHaven] Installing/updating Python dependencies (yt-dlp, imageio-ffmpeg, mutagen)…"
    );
    const pipArgs = ["-m", "pip", "install", "--disable-pip-version-check"];
    if (forceUpgrade) pipArgs.push("--upgrade");
    else pipArgs.push("--quiet");
    pipArgs.push("-r", reqFile);
    const pip = spawnSync(venvPython, pipArgs, {
      stdio: "inherit",
    });
    if (pip.status !== 0) {
      return null;
    }
    fs.writeFileSync(reqHashFile, wantHash, "utf8");
  }
  return venvPython;
}

function getBinaryAssetName() {
  if (process.platform === "win32") return "ClipHaven-Windows.exe";
  if (process.platform === "darwin") return "ClipHaven-macOS";
  if (process.platform === "linux") {
    if (process.arch === "arm64") return "ClipHaven-Linux-ARM64";
    if (process.arch === "x64") return "ClipHaven-Linux-x64";
  }
  return null;
}

function downloadFile(url, destPath, redirectsLeft = 6) {
  return new Promise((resolve, reject) => {
    if (redirectsLeft <= 0) return reject(new Error("Too many redirects while downloading ClipHaven binary."));
    const req = https.get(
      url,
      { headers: { "User-Agent": `ClipHaven-CLI/${VERSION}` } },
      (res) => {
        if (res.statusCode >= 300 && res.statusCode < 400 && res.headers.location) {
          res.resume();
          const nextUrl = new URL(res.headers.location, url).toString();
          return downloadFile(nextUrl, destPath, redirectsLeft - 1).then(resolve, reject);
        }
        if (res.statusCode !== 200) {
          res.resume();
          return reject(new Error(`HTTP ${res.statusCode} downloading ${url}`));
        }
        const total = Number(res.headers["content-length"] || 0);
        let received = 0;
        let lastPct = -1;
        const tmpPath = `${destPath}.tmp`;
        const out = fs.createWriteStream(tmpPath);
        res.on("data", (chunk) => {
          received += chunk.length;
          if (total > 0) {
            const pct = Math.floor((received / total) * 100);
            if (pct >= lastPct + 10 || pct === 100) {
              lastPct = pct;
              process.stdout.write(`\r[ClipHaven] Downloading runtime binary… ${pct}%`);
            }
          }
        });
        res.pipe(out);
        out.on("finish", () => {
          out.close(() => {
            if (total > 0) process.stdout.write("\n");
            fs.renameSync(tmpPath, destPath);
            resolve(destPath);
          });
        });
        out.on("error", (err) => {
          try { fs.unlinkSync(tmpPath); } catch (_) {}
          reject(err);
        });
      }
    );
    req.on("error", reject);
  });
}

async function ensurePrebuiltBinary(forceRefresh = false) {
  const asset = getBinaryAssetName();
  if (!asset) {
    throw new Error(`No prebuilt ClipHaven binary available for ${process.platform}/${process.arch}. Please install Python 3.10+.`);
  }
  const binDir = path.join(HOME_DATA_DIR, "bin", `v${VERSION}`);
  const binPath = path.join(binDir, asset);
  if (!forceRefresh && fs.existsSync(binPath) && fs.statSync(binPath).size > 1024 * 1024) {
    return binPath;
  }
  if (forceRefresh && fs.existsSync(binPath)) {
    try { fs.unlinkSync(binPath); } catch (_) {}
  }

  fs.mkdirSync(binDir, { recursive: true });
  const versionUrl = `https://github.com/${REPO}/releases/download/v${VERSION}/${asset}`;
  const latestUrl = `https://github.com/${REPO}/releases/latest/download/${asset}`;
  console.log(`[ClipHaven] Python 3.10+ not available. Fetching prebuilt binary (${asset})…`);
  try {
    await downloadFile(versionUrl, binPath);
  } catch (_) {
    await downloadFile(latestUrl, binPath);
  }
  if (process.platform !== "win32") {
    fs.chmodSync(binPath, 0o755);
  }
  cleanupOldCachedBinaries(`v${VERSION}`);
  return binPath;
}


function cleanupOldCachedBinaries(keepVerDir) {
  try {
    const base = path.join(HOME_DATA_DIR, "bin");
    if (!fs.existsSync(base)) return;
    for (const entry of fs.readdirSync(base)) {
      if (entry !== keepVerDir && /^v\d+\.\d+\.\d+/.test(entry)) {
        fs.rmSync(path.join(base, entry), { recursive: true, force: true });
      }
    }
  } catch (_) {}
}

function hasCmd(name) {
  const probe = process.platform === "win32" ? "where" : "which";
  try {
    return spawnSync(probe, [name], { stdio: "ignore", timeout: 3000 }).status === 0;
  } catch (_) {
    return false;
  }
}

function runDoctor() {
  const pyInfo = findPython310();
  const venvDir = path.join(HOME_DATA_DIR, "venv");
  const venvPy = process.platform === "win32"
    ? path.join(venvDir, "Scripts", "python.exe")
    : path.join(venvDir, "bin", "python");
  const asset = getBinaryAssetName();
  const cachedBin = asset ? path.join(HOME_DATA_DIR, "bin", `v${VERSION}`, asset) : "";
  const hasVenv = fs.existsSync(venvPy);
  const hasBin = cachedBin && fs.existsSync(cachedBin);
  const runningViaNpx = /[\\/]_npx[\\/]/i.test(PKG_ROOT);

  console.log(`ClipHaven Doctor (v${VERSION})`);
  console.log(`  OS / Arch       : ${process.platform} / ${process.arch}`);
  console.log(`  Node.js         : ${process.version} (${runningViaNpx ? "npx" : "installed"})`);
  console.log(`  Python 3.10+    : ${pyInfo ? `Found (${pyInfo.version} via ${pyInfo.cmd})` : "Not found (will use Option B binary fallback)"}`);
  console.log(`  Python .venv    : ${hasVenv ? `Ready (${venvDir})` : "Not created yet"}`);
  console.log(`  Cached Binary   : ${hasBin ? `Ready (${cachedBin})` : `Not cached (${asset || "unsupported arch"})`}`);
  console.log(`  System FFmpeg   : ${hasCmd("ffmpeg") ? "Available" : "Bundled via imageio-ffmpeg / release binary"}`);
  console.log(`  System aria2c   : ${hasCmd("aria2c") ? "Available (auto-acceleration enabled)" : "Not installed (optional)"}`);
}

function launchChild(cmd, args, env, cwd) {
  const child = spawn(cmd, args, { stdio: "inherit", env, cwd });
  const forwardSignal = (sig) => {
    try { child.kill(sig); } catch (_) {}
  };
  process.on("SIGINT", () => forwardSignal("SIGINT"));
  process.on("SIGTERM", () => forwardSignal("SIGTERM"));
  child.on("exit", (code, signal) => {
    if (signal) process.exit(1);
    process.exit(code == null ? 0 : code);
  });
  child.on("error", (err) => {
    console.error(`[ClipHaven] Failed to start: ${err.message}`);
    process.exit(1);
  });
}


const UPDATE_CACHE_FILE = path.join(HOME_DATA_DIR, "cli_update_cache.json");
const UPDATE_TTL_MS = 4 * 60 * 60 * 1000; // 4 hours

function parseSemver(ver) {
  const parts = String(ver || "").trim().replace(/^[vV]/, "").split("-")[0].split(".");
  return [0, 1, 2].map((i) => parseInt(parts[i] || "0", 10) || 0);
}

function isNewerSemver(latest, current) {
  const a = parseSemver(latest);
  const b = parseSemver(current);
  for (let i = 0; i < 3; i++) {
    if (a[i] !== b[i]) return a[i] > b[i];
  }
  return false;
}

function fetchLatestPublicRelease() {
  return new Promise((resolve) => {
    try {
      if (fs.existsSync(UPDATE_CACHE_FILE)) {
        const cached = JSON.parse(fs.readFileSync(UPDATE_CACHE_FILE, "utf8"));
        if (cached && cached.checkedAt && (Date.now() - cached.checkedAt) < UPDATE_TTL_MS) {
          return resolve(cached);
        }
      }
    } catch (_) {}

    const req = https.get(
      `https://api.github.com/repos/${REPO}/releases/latest`,
      {
        timeout: 1800,
        headers: {
          "User-Agent": `ClipHaven-CLI/${VERSION}`,
          Accept: "application/vnd.github+json",
        },
      },
      (res) => {
        if (res.statusCode !== 200) {
          res.resume();
          return resolve(null);
        }
        let raw = "";
        res.setEncoding("utf8");
        res.on("data", (chunk) => { raw += chunk; });
        res.on("end", () => {
          try {
            const data = JSON.parse(raw);
            if (data.draft || data.prerelease) return resolve(null);
            const tag = String(data.tag_name || "").trim();
            const m = tag.match(/^[vV](\d+\.\d+\.\d+)$/);
            if (!m) return resolve(null);
            const info = {
              checkedAt: Date.now(),
              latestVersion: m[1],
              releaseUrl: data.html_url || `https://github.com/${REPO}/releases/tag/${tag}`,
            };
            try {
              fs.mkdirSync(HOME_DATA_DIR, { recursive: true });
              fs.writeFileSync(UPDATE_CACHE_FILE, JSON.stringify(info), "utf8");
            } catch (_) {}
            resolve(info);
          } catch (_) {
            resolve(null);
          }
        });
      }
    );
    req.on("timeout", () => { req.destroy(); resolve(null); });
    req.on("error", () => resolve(null));
  });
}

function askYesNo(question) {
  return new Promise((resolve) => {
    const rl = readline.createInterface({ input: process.stdin, output: process.stdout });
    const promptUser = (q) => {
      rl.question(q, (ans) => {
        const v = String(ans || "").trim().toLowerCase();
        if (v === "" || v === "y" || v === "yes" || v === "yas") {
          rl.close();
          return resolve(true);
        }
        if (v === "n" || v === "no") {
          rl.close();
          return resolve(false);
        }
        promptUser("Please type Y / Yes / Yas or N / No: ");
      });
    };
    promptUser(question);
  });
}

async function checkAndPromptCliUpdate() {
  const info = await fetchLatestPublicRelease();
  if (!info || !info.latestVersion || !isNewerSemver(info.latestVersion, VERSION)) {
    return false;
  }

  const line1 = `  Update available: v${VERSION} -> v${info.latestVersion}`;
  const line2 = `  Release: ${info.releaseUrl}`;
  const width = Math.max(line1.length, line2.length) + 2;
  const bar = "─".repeat(width);
  console.log(`\n╭${bar}╮`);
  console.log(`│${line1.padEnd(width)}│`);
  console.log(`│${line2.padEnd(width)}│`);
  console.log(`╰${bar}╯`);

  if (!process.stdin.isTTY || !process.stdout.isTTY) {
    console.log("Run: npm install -g @asadullahalmunib/cliphaven@latest\n");
    return false;
  }

  const yes = await askYesNo("Do you want to update @asadullahalmunib/cliphaven now? (Y/n): ");
  if (!yes) {
    console.log("[ClipHaven] Skipping update. Starting ClipHaven…\n");
    return false;
  }

  const runningViaNpx = /[\\/]_npx[\\/]/i.test(PKG_ROOT);
  try { fs.unlinkSync(UPDATE_CACHE_FILE); } catch (_) {}
  if (runningViaNpx) {
    console.log(`\n[ClipHaven] Launching latest v${info.latestVersion} via npx…`);
    const npxCmd = process.platform === "win32" ? "npx.cmd" : "npx";
    const forwardArgs = process.argv.slice(2).filter((a) => a !== "--no-update-check");
    const res = spawnSync(npxCmd, ["--yes", `${pkg.name}@latest`, "--no-update-check", ...forwardArgs], { stdio: "inherit" });
    if (res.status === 0) return true;
    console.warn("\n[ClipHaven] Could not launch latest via npx. Run manually:\n  npx @asadullahalmunib/cliphaven@latest\n");
    return false;
  }
  console.log(`\n[ClipHaven] Updating @asadullahalmunib/cliphaven to v${info.latestVersion}…`);
  const npmCmd = process.platform === "win32" ? "npm.cmd" : "npm";
  const res = spawnSync(npmCmd, ["install", "-g", `${pkg.name}@latest`], { stdio: "inherit" });
  if (res.status === 0) {
    console.log(`\n[ClipHaven] Updated to v${info.latestVersion}! Please run 'cliphaven' again to use the new version.`);
    return true;
  }
  console.warn("\n[ClipHaven] Automatic npm update failed. You can update manually with:\n  npm install -g @asadullahalmunib/cliphaven@latest\n");
  return false;
}

async function main() {
  const opts = parseArgs(process.argv.slice(2));
  if (opts.help) {
    printHelp();
    process.exit(0);
  }
  if (opts.version) {
    console.log(`ClipHaven v${VERSION}`);
    process.exit(0);
  }
  if (opts.doctor) {
    runDoctor();
    process.exit(0);
  }

  // Handle one-command engine update (--update / -u)
  if (opts.update) {
    if (!opts.forceBinary) {
      const pyInfo = findPython310();
      if (pyInfo) {
        const venvPython = ensurePythonVenv(pyInfo, true);
        if (venvPython) {
          console.log("[ClipHaven] Engine updated successfully.");
          process.exit(0);
        }
      }
    }
    try {
      await ensurePrebuiltBinary(true);
      console.log("[ClipHaven] Cached runtime binary refreshed successfully.");
      process.exit(0);
    } catch (err) {
      console.error(`[ClipHaven] Update failed: ${err.message}`);
      process.exit(1);
    }
  }

  if (!opts.noUpdateCheck) {
    const didUpdate = await checkAndPromptCliUpdate();
    if (didUpdate) process.exit(0);
  }

  const childEnv = { ...process.env, CLIPHAVEN_FROM_NPM: "1" };
  if (opts.port) childEnv.CLIPHAVEN_PORT = opts.port;
  if (opts.noBrowser) childEnv.CLIPHAVEN_NO_BROWSER = "1";
  if (opts.url) childEnv.CLIPHAVEN_INITIAL_URL = opts.url;

  // Option A: Check Python 3.10+ first -> run isolated .venv + server.py
  if (!opts.forceBinary) {
    const pyInfo = findPython310();
    if (pyInfo) {
      const venvPython = ensurePythonVenv(pyInfo, false);
      if (venvPython) {
        const serverPy = path.join(PKG_ROOT, "server.py");
        launchChild(venvPython, [serverPy], childEnv, PKG_ROOT);
        return;
      }
      console.warn("[ClipHaven] Python environment setup failed; falling back to prebuilt binary…");
    }
  }

  // Option B: Automatic fallback -> download & run cached GitHub Release binary
  try {
    const binPath = await ensurePrebuiltBinary(false);
    launchChild(binPath, [], childEnv, path.dirname(binPath));
  } catch (err) {
    console.error(`[ClipHaven] Error: ${err.message}`);
    process.exit(1);
  }
}

main();
