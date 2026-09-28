/**
 * Create backend/.venv and install backend/requirements.txt into it.
 *
 * The pins in requirements.txt target Python 3.12: that is the version the
 * installer embeds (scripts/build-full-package.ps1) and the version
 * backend/Dockerfile runs in production. Interpreting them on a newer
 * interpreter fails, because pandas/pillow/aiohttp have no wheels for it and
 * pip would have to build them from source.
 *
 * Usage: node scripts/setup-python.js
 */

"use strict";

const path = require("path");
const fs = require("fs");
const { spawnSync } = require("child_process");

const TARGET_PYTHON = "3.12";

const repoRoot = path.resolve(__dirname, "..");
const backendDir = path.join(repoRoot, "backend");
const venvDir = path.join(backendDir, ".venv");
const isWindows = process.platform === "win32";
const venvPython = path.join(
  venvDir,
  isWindows ? "Scripts" : "bin",
  isWindows ? "python.exe" : "python"
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
  const launcher = isWindows ? "py" : "python3";
  run(launcher, ["-" + TARGET_PYTHON, "-m", "venv", venvDir], `Creating venv with Python ${TARGET_PYTHON}`);

  if (!fs.existsSync(venvPython)) {
    process.stderr.write(
      `\nvenv was not created at ${venvPython}.\n` +
        `Is Python ${TARGET_PYTHON} installed? On Windows:  winget install Python.Python.${TARGET_PYTHON.replace(".", "")}\n`
    );
    process.exit(1);
  }
}

run(venvPython, ["-m", "pip", "install", "--upgrade", "pip"], "Upgrading pip");
run(venvPython, ["-m", "pip", "install", "-r", requirements], "Installing backend requirements");

process.stdout.write(`\nBackend environment ready: ${venvPython}\nRun the dev stack with:  npm run dev\n`);
