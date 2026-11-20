#!/usr/bin/env node
// Один вход в качество. `npm run gate` — то же, что запускает CI, `npm run
// gate:fast` — pre-push и быстрый локальный цикл, `npm run gate:e2e` —
// отдельный стенд.
//
// Ярусы накопительные:
//   fast — статика по всему репозиторию, офлайн                    бюджет: 60 с
//   gate — fast + modern-web/reactuse-diff (внешние данные) + pytest + vitest + сборка
//   e2e  — gate + Playwright smoke, нужен живой стенд и браузер
//
// Список статических шагов НЕ дублируется здесь: хозяин — hk.pkl, а шаг
// запускается как `hk check --all --step <имя>`. Поэтому здесь только имена
// шагов hk, и разъехаться с hk.pkl нельзя: неизвестное имя упадёт в hk.
//
// Шаг — это данные, а не проза. Контракт полей (harness/rules/quality-gates.md):
//   name — ключ для docs/quality-gates.md и docs/quality/proven-checks.json;
//   tier — fast|gate|e2e;
//   command — точная команда, одна и та же локально и в CI;
//   ci — где шаг живёт в CI (workflow или `npm run gate`, если отдельного нет);
//   what — что ломается без шага, одной фразой.
//
// Гейт ничего не правит: `hk check` по конвенции только докладывает, а
// --fix/--write/stage_fixed здесь нет и не будет. Фиксы — `npm run fix`.

import { spawnSync } from "node:child_process";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const IS_WIN = process.platform === "win32";
const FAST_BUDGET_MS = 60_000;

/**
 * @typedef {object} Step
 * @property {string} name        stable id; обязан совпадать со строкой карты защит
 * @property {"fast"|"gate"|"e2e"} tier
 * @property {string} command     команда целиком; локально и в CI одна и та же
 * @property {string} ci          workflow или `npm run gate`, если шаг только в гейте
 * @property {string} what        что ломается, если шаг убрать
 * @property {string} [tool]      исполняемый файл в начале command, наличие проверяем
 * @property {string} [cwd]       относительно корня репозитория
 * @property {Record<string,string>} [env]
 * @property {string[]} [requires] URL, которые должны отвечать до запуска
 * @property {number[]} [missingExitCodes] коды, означающие «не проверено», а не «сломано»
 * @property {number} [timeout]
 */

/** @type {Step[]} */
export const STEPS = [
  // ── fast: статика, офлайн ─────────────────────────────────────────────────
  {
    name: "docs-sync",
    tier: "fast",
    command: "node scripts/check-docs.mjs",
    ci: "check.yml",
    what: "шаг в STEPS без строки в карте защит, строка без шага, или шаг без доказательства",
  },
  {
    name: "ruff",
    tier: "fast",
    command: "hk check --all --step ruff",
    tool: "hk",
    ci: "check.yml",
    what: "ошибки Python (ruff: E4/E7/E9/F/I/UP/B/C4/SIM)",
  },
  {
    name: "oxfmt",
    tier: "fast",
    command: "hk check --all --step oxfmt",
    tool: "hk",
    ci: "check.yml",
    what: "расхождение формата (js/ts/md/yaml/toml/json/html/css)",
  },
  {
    name: "oxlint",
    tier: "fast",
    command: "hk check --all --step oxlint",
    tool: "hk",
    ci: "check.yml",
    what: "категория correctness и no-unused-vars в JS/TS",
  },
  {
    name: "betterleaks",
    tier: "fast",
    command: "hk check --all --step betterleaks",
    tool: "hk",
    ci: "check.yml",
    what: "закоммиченный секрет (ключ, токен, пароль)",
  },
  {
    name: "shellcheck",
    tier: "fast",
    command: "hk check --all --step shellcheck",
    tool: "hk",
    ci: "check.yml",
    what: "ошибки и переносимость shell-скриптов",
  },
  {
    name: "hadolint",
    tier: "fast",
    command: "hk check --all --step hadolint",
    tool: "hk",
    ci: "check.yml",
    what: "практики Dockerfile",
  },
  {
    name: "jactionlint",
    tier: "fast",
    command: "hk check --all --step jactionlint",
    tool: "hk",
    ci: "check.yml",
    what: "корректность, security и policy GitHub Actions",
  },
  {
    name: "knip",
    tier: "fast",
    command: "hk check --all --step knip",
    tool: "hk",
    ci: "check.yml",
    what: "неиспользуемые файлы, экспорты и dev-зависимости",
  },
  {
    name: "tsc",
    tier: "fast",
    command: "hk check --all --step tsc",
    tool: "hk",
    ci: "check.yml",
    what: "ошибка типов TypeScript (tsc --noEmit, strict)",
  },

  // ── gate: внешние данные и тестовые наборы ────────────────────────────────
  {
    name: "modern-web",
    tier: "gate",
    command: "hk check --all --step modern-web",
    tool: "hk",
    ci: "check.yml",
    what: "новый legacy-паттерн веб-платформы сверх docs/quality/modern-web-baseline.json",
    // 2 = сканер недоступен (сеть/пакет): это missing, а не регресс кода.
    missingExitCodes: [2],
    timeout: 180_000,
  },
  {
    name: "reactuse-diff",
    tier: "gate",
    command: "hk check --all --step reactuse-diff",
    tool: "hk",
    ci: "check.yml",
    what: "новый ручной примитив (matchMedia, observers, clipboard) вместо ReactUse",
    // 2 = git не смог построить дифф: это missing, а не регресс кода.
    missingExitCodes: [2],
    timeout: 120_000,
  },
  {
    name: "backend-tests",
    tier: "gate",
    command: "npm run test:backend",
    ci: "check.yml",
    what: "регрессия backend (pytest, in-memory sqlite, без стенда)",
    timeout: 900_000,
  },
  {
    name: "frontend-unit",
    tier: "gate",
    command: "npm run test:frontend",
    ci: "check.yml",
    what: "регрессия frontend (vitest run)",
    timeout: 600_000,
  },
  {
    name: "frontend-build",
    tier: "gate",
    // build:vite — только vite build: типы уже прогнал шаг tsc,
    // повторный `tsc -b` в `frontend run build` дублировал бы работу.
    command: "npm --prefix frontend run build:vite",
    ci: "check.yml",
    what: "production-сборка frontend (vite build) падает",
    timeout: 600_000,
  },

  // ── e2e: нужен живой стенд ───────────────────────────────────────────────
  {
    name: "e2e-playwright",
    tier: "e2e",
    command: "npm run test:e2e",
    ci: "missing: e2e требует живого стенда и Chrome с CDP :9222",
    what: "сломан пользовательский путь (Playwright: smoke, catalog, live_demo)",
    requires: [
      "http://127.0.0.1:8013/health",
      "http://127.0.0.1:5173/",
      "http://127.0.0.1:9222/json/version",
    ],
    timeout: 900_000,
  },
];

const TIER_ORDER = { fast: 0, gate: 1, e2e: 2 };

function parseArgs(argv) {
  const opts = {
    tier: "gate",
    only: null,
    list: false,
    strict: false,
    json: false,
    doctor: false,
  };
  for (let i = 0; i < argv.length; i += 1) {
    const arg = argv[i];
    if (arg === "--tier") opts.tier = argv[++i];
    else if (arg === "--fast") opts.tier = "fast";
    else if (arg === "--e2e") opts.tier = "e2e";
    else if (arg === "--only") {
      opts.only = argv[++i]
        .split(",")
        .map((value) => value.trim())
        .filter(Boolean);
    } else if (arg === "--list") opts.list = true;
    else if (arg === "--strict") opts.strict = true;
    else if (arg === "--json") opts.json = true;
    else if (arg === "--doctor") opts.doctor = true;
    else if (arg === "--help" || arg === "-h") {
      console.log(
        "usage: node scripts/gate.mjs [--tier fast|gate|e2e] [--only a,b] [--list] [--strict] [--json] [--doctor]",
      );
      process.exit(0);
    }
  }
  if (!(opts.tier in TIER_ORDER)) {
    console.error(`gate: неизвестный ярус «${opts.tier}» (fast|gate|e2e)`);
    process.exit(2);
  }
  return opts;
}

function colorize(code, text) {
  if (!process.stdout.isTTY || process.env.NO_COLOR) return text;
  return `\u001b[${code}m${text}\u001b[0m`;
}

const c = {
  bold: (text) => colorize("1", text),
  dim: (text) => colorize("2", text),
  green: (text) => colorize("32", text),
  yellow: (text) => colorize("33", text),
  red: (text) => colorize("31", text),
};

function which(bin) {
  const result = spawnSync(IS_WIN ? "where" : "which", [bin], {
    encoding: "utf8",
    windowsHide: true,
  });
  return result.status === 0;
}

const toolCache = new Map();

/**
 * Инструменты гейта ставятся через mise (ruff, hk, oxlint…), а не через
 * node_modules, поэтому в «голом» терминале их может не быть в PATH. Пробуем
 * PATH, затем `mise which`; ненайденный инструмент — это `missing` с подсказкой,
 * а не «команда не найдена».
 */
function resolveTool(name) {
  if (toolCache.has(name)) return toolCache.get(name);
  let resolved = null;
  if (which(name)) {
    resolved = { path: name, via: "PATH" };
  } else if (which("mise")) {
    const probe = spawnSync("mise", ["which", name], { encoding: "utf8", windowsHide: true });
    const line = (probe.stdout || "")
      .split(/\r?\n/)
      .map((value) => value.trim())
      .find(Boolean);
    if (probe.status === 0 && line && fs.existsSync(line)) {
      resolved = { path: line, via: "mise" };
    }
  }
  toolCache.set(name, resolved);
  return resolved;
}

/** Команда шага с подставленным фактическим путём инструмента. */
export function commandFor(step) {
  if (!step.tool) return step.command;
  const resolved = resolveTool(step.tool);
  if (!resolved) return step.command;
  const bin = /\s/.test(resolved.path) ? `"${resolved.path}"` : resolved.path;
  const prefix = `${step.tool} `;
  return step.command.startsWith(prefix)
    ? `${bin}${step.command.slice(step.tool.length)}`
    : step.command;
}

async function reachable(url, timeoutMs = 1500) {
  try {
    const response = await fetch(url, { signal: AbortSignal.timeout(timeoutMs) });
    return response.ok || response.status < 500;
  } catch {
    return false;
  }
}

function selected(step, opts) {
  if (opts.only) return opts.only.includes(step.name);
  return TIER_ORDER[step.tier] <= TIER_ORDER[opts.tier];
}

function formatMs(ms) {
  return ms >= 1000 ? `${(ms / 1000).toFixed(1)}s` : `${ms}ms`;
}

function tail(text, lines = 40) {
  const all = text.split(/\r?\n/);
  return all.slice(Math.max(0, all.length - lines)).join("\n");
}

async function runStep(step) {
  if (step.requires) {
    for (const url of step.requires) {
      if (!(await reachable(url))) {
        return {
          status: "missing",
          ms: 0,
          output: `${url} не отвечает — подними стенд (npm run dev / npm run dev:sim:fast) и Chrome (npm run chrome:debug)`,
        };
      }
    }
  }
  if (step.tool && !resolveTool(step.tool)) {
    return {
      status: "missing",
      ms: 0,
      output: `${step.tool} не найден: PATH и \`mise which ${step.tool}\` пусты — запусти mise install`,
    };
  }
  const startedAt = Date.now();
  const result = spawnSync(commandFor(step), {
    cwd: step.cwd ? path.join(ROOT, step.cwd) : ROOT,
    env: { ...process.env, ...step.env },
    encoding: "utf8",
    shell: true,
    windowsHide: true,
    timeout: step.timeout ?? 600_000,
    maxBuffer: 64 * 1024 * 1024,
  });
  const ms = Date.now() - startedAt;
  const output = `${result.stdout ?? ""}\n${result.stderr ?? ""}`;
  if (result.error) {
    return { status: "missing", ms, output: result.error.message };
  }
  if (result.status === 0) return { status: "ok", ms, output };
  if (step.missingExitCodes?.includes(result.status)) {
    return { status: "missing", ms, output };
  }
  return { status: "fail", ms, output };
}

async function main() {
  const opts = parseArgs(process.argv.slice(2));

  if (opts.list) {
    for (const step of STEPS) {
      console.log(`${step.tier.padEnd(4)} ${step.name.padEnd(20)} ${step.what} [${step.ci}]`);
    }
    return;
  }
  if (opts.doctor) {
    runDoctor();
    return;
  }

  const steps = STEPS.filter((step) => selected(step, opts));
  if (steps.length === 0) {
    console.error("gate: ни один шаг не выбран");
    process.exitCode = 2;
    return;
  }

  const startedAt = Date.now();
  if (!opts.json) {
    console.log(`${c.bold("gate")} tier=${opts.tier} steps=${steps.length}`);
  }

  const results = [];
  for (const step of steps) {
    const outcome = await runStep(step);
    results.push({ name: step.name, tier: step.tier, ci: step.ci, ...outcome });
    if (opts.json) continue;
    const label = `${String(results.length).padStart(2)}/${String(steps.length).padEnd(2)} ${step.name}`;
    if (outcome.status === "ok") {
      console.log(`${c.green("✔")} ${label.padEnd(34)} ${c.dim(formatMs(outcome.ms))}`);
    } else if (outcome.status === "missing") {
      console.log(`${c.yellow("?")} ${label.padEnd(34)} ${c.dim("missing")}`);
      if (outcome.output) console.log(tail(outcome.output, 5).replace(/^/gm, "   "));
    } else {
      console.log(`${c.red("✖")} ${label.padEnd(34)} ${c.dim(formatMs(outcome.ms))}`);
      if (outcome.output) console.log(tail(outcome.output).replace(/^/gm, "   "));
    }
  }

  const elapsed = Date.now() - startedAt;
  const failed = results.filter((result) => result.status === "fail");
  const missing = results.filter((result) => result.status === "missing");
  const budget = opts.tier === "fast" ? FAST_BUDGET_MS : null;
  const overBudget = Boolean(budget && elapsed > budget);

  if (opts.json) {
    console.log(
      JSON.stringify(
        {
          tier: opts.tier,
          elapsedMs: elapsed,
          budgetMs: budget,
          steps: results.map(({ output: _output, ...rest }) => rest),
          passed: results.length - failed.length - missing.length,
          failed: failed.length,
          missing: missing.length,
        },
        null,
        2,
      ),
    );
  } else {
    console.log("");
    console.log(
      `${c.bold("summary")} ${results.length - failed.length - missing.length}/${results.length} passed in ${formatMs(elapsed)}` +
        (budget ? ` (budget ${formatMs(budget)})` : ""),
    );
    if (failed.length) console.log(c.red(`failed: ${failed.map((r) => r.name).join(", ")}`));
    if (missing.length) console.log(c.yellow(`missing: ${missing.map((r) => r.name).join(", ")}`));
    if (overBudget) {
      console.log(
        c.yellow(`fast превысил бюджет: ${formatMs(elapsed)} > ${formatMs(budget)}`) +
          " — ускорь шаг или перенеси его в gate/e2e, не поднимай лимит",
      );
    }
  }

  if (failed.length) process.exitCode = 1;
  if (opts.strict && (missing.length || overBudget)) process.exitCode = 1;
}

function runDoctor() {
  console.log(c.bold("doctor"));
  const bins = ["node", "npm", "npx", "git", "mise", "hk", "ruff", "oxlint", "oxfmt", "knip"];
  for (const bin of bins) {
    const resolved = resolveTool(bin);
    const mark = resolved ? c.green("✔") : c.red("✖");
    const note = resolved && resolved.via === "mise" ? c.dim(` (mise: ${resolved.path})`) : "";
    console.log(`  ${mark} ${bin}${note}`);
  }
  console.log(`  ${c.dim("·")} node ${process.versions.node}`);

  const docs = spawnSync(process.execPath, ["scripts/check-docs.mjs"], {
    cwd: ROOT,
    encoding: "utf8",
    windowsHide: true,
  });
  console.log(`  ${docs.status === 0 ? c.green("✔") : c.red("✖")} docs-sync`);
  if (docs.status !== 0) process.exitCode = 1;

  const dirty = spawnSync("git", ["status", "--porcelain"], {
    cwd: ROOT,
    encoding: "utf8",
    windowsHide: true,
  });
  const dirtyLines = (dirty.stdout ?? "").trim();
  if (dirtyLines) {
    console.log(
      c.yellow(`  ! рабочее дерево грязное (${dirtyLines.split(/\r?\n/).length} файлов)`),
    );
  }
  console.log(
    c.yellow(
      "  ! guard-tree — не шаг гейта: проверка «запись в чужое дерево» требует списка разрешённых корней",
    ),
  );
}

const isMain = process.argv[1] && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url);

if (isMain) {
  main().catch((error) => {
    console.error(error);
    process.exitCode = 1;
  });
}
