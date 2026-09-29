/**
 * Run the backend with the project's virtualenv, falling back to `python`.
 *
 * Why this exists: `backend/requirements.txt` is pinned for Python 3.12 (the
 * version the installer embeds — see scripts/build-full-package.ps1 — and the
 * version backend/Dockerfile runs in production). Newer interpreters, e.g. the
 * 3.14 that happens to be first on PATH on some machines, have no wheels for
 * those pins, so `pip install -r backend/requirements.txt` cannot succeed there
 * and importing the app fails on missing C-extension packages (PIL, pandas).
 *
 * A bare `python` in the npm scripts silently picks up whichever interpreter
 * PATH resolves to, so the venv is referenced explicitly here instead.
 *
 * Usage: node scripts/run-python.js <args...>   (run from any directory)
 *   e.g. node scripts/run-python.js -m uvicorn app.main:app --port 8013
 *
 * Env overrides: leading `--env KEY=VALUE` pairs are removed from the
 * argument list and applied to the spawned process. Needed because npm runs
 * scripts through cmd.exe on Windows, where the `KEY=VALUE cmd` prefix form
 * is a POSIX-ism and silently sets nothing.
 *
 *   node scripts/run-python.js --env SIMULATION_ENABLED=false -m uvicorn app.main:app
 */

"use strict";

const path = require("path");
const { spawn } = require("child_process");

const repoRoot = path.resolve(__dirname, "..");
const backendDir = path.join(repoRoot, "backend");

const isWindows = process.platform === "win32";
const venvPython = path.join(
  backendDir,
  ".venv",
  isWindows ? "Scripts" : "bin",
  isWindows ? "python.exe" : "python"
);

const fs = require("fs");
const python = fs.existsSync(venvPython) ? venvPython : "python";

if (!fs.existsSync(venvPython)) {
  process.stderr.write(
    `[run-python] venv not found at ${venvPython}, falling back to "python" from PATH.\n` +
      `[run-python] create it with:  py -3.12 -m venv backend/.venv\n` +
      `[run-python] then install deps: backend\\.venv\\Scripts\\python.exe -m pip install -r backend\\requirements.txt\n`
  );
}

/**
 * Отделяет ведущие `--env KEY=VALUE` от аргументов Python.
 * Ошибку в паре не проглатываем: молчаливый запуск в чужом режиме дороже
 * остановки.
 */
function splitEnv(argv) {
  const args = [];
  const env = { ...process.env };
  let i = 0;
  for (; i < argv.length; i++) {
    if (argv[i] !== "--env") break;
    const pair = argv[i + 1];
    const eq = pair ? pair.indexOf("=") : -1;
    if (eq < 1) {
      process.stderr.write(
        `[run-python] --env expects KEY=VALUE, got ${JSON.stringify(pair)}\n`
      );
      process.exit(2);
    }
    env[pair.slice(0, eq)] = pair.slice(eq + 1);
    i++;
  }
  return { args: argv.slice(i), env };
}

const { args: pythonArgs, env } = splitEnv(process.argv.slice(2));

const child = spawn(python, pythonArgs, {
  cwd: backendDir,
  stdio: "inherit",
  env,
  // Ctrl+C in the concurrently-driven dev stack must reach the real process.
  windowsHide: true,
});

child.on("error", (err) => {
  process.stderr.write(`[run-python] failed to start ${python}: ${err.message}\n`);
  process.exit(1);
});

child.on("exit", (code, signal) => {
  if (signal) {
    process.kill(process.pid, signal);
    return;
  }
  process.exit(code === null ? 1 : code);
});
