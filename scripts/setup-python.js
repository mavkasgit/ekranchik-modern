/**
 * Create backend/.venv and install backend/requirements.txt into it.
 *
 * The pins in requirements.txt target Python 3.14: that is the version
 * backend/Dockerfile runs in production, and the one with wheels for every
 * pinned package (pandas, aiohttp, python-calamine). The Windows
 * installer still embeds Python 3.12 (scripts/build-full-package.ps1): the
 * requirements support both, so the two runtimes do not drift in what they
 * install.
 *
 * Usage: node scripts/setup-python.js
 */

"use strict";

const path = require("path");
const fs = require("fs");
const { spawnSync } = require("child_process");

const TARGET_PYTHON = "3.14";

const repoRoot = path.resolve(__dirname, "..");
const backendDir = path.join(repoRoot, "backend");
const venvDir = path.join(backendDir, ".venv");
const isWindows = process.platform === "win32";
const venvPython = path.join(
  venvDir,
  isWindows ? "Scripts" : "bin",
  isWindows ? "python.exe" : "python",
);
const requirements = path.join(backendDir, "requirements.txt");

function run(cmd, args, label) {
  process.stdout.write(`==> ${label}\n`);
  const res = spawnSync(cmd, args, { stdio: "inherit", shell: false });
  if (res.error) {
    process.stderr.write(`Failed to run ${cmd}: ${res.error.message}\n`);
    process.exit(1);
  }
  if (res.status !== 0) {
    process.stderr.write(`${label} failed with exit code ${res.status}\n`);
    process.exit(res.status === null ? 1 : res.status);
  }
}

if (fs.existsSync(venvPython)) {
  process.stdout.write(`venv already exists: ${venvDir}\n`);
} else {
  // venv создаётся системным Python 3.14; дальше mise активирует его через
  // `_.python.venv` (см. mise.toml), поэтому `python` в задачах — из venv.
  // На Windows сначала пробуем launcher `py -3.14`: дефолтный `python` может
  // оказаться другой версией.
  let launcher = isWindows ? "python" : "python3";
  let launcherArgs = [];
  if (isWindows) {
    const probe = spawnSync("py", ["-3.14", "--version"], { stdio: "ignore", shell: false });
    if (!probe.error && probe.status === 0) {
      launcher = "py";
      launcherArgs = ["-3.14"];
    }
  }
  run(
    launcher,
    [...launcherArgs, "-m", "venv", venvDir],
    `Creating venv with Python ${TARGET_PYTHON}`,
  );

  if (!fs.existsSync(venvPython)) {
    process.stderr.write(
      `\nvenv was not created at ${venvPython}.\n` +
        `Python ${TARGET_PYTHON} is required. Install it (winget install Python.Python.314), then re-run:  mise run install\n`,
    );
    process.exit(1);
  }
}

run(venvPython, ["-m", "pip", "install", "--upgrade", "pip"], "Upgrading pip");
run(venvPython, ["-m", "pip", "install", "-r", requirements], "Installing backend requirements");

process.stdout.write(
  `\nBackend environment ready: ${venvPython}\nRun the dev stack with:  npm run dev\n`,
);
