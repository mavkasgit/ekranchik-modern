#!/usr/bin/env node
// Сверка реестра инструментов гейта (docs/quality/tools.json).
//
// Контракт — harness/rules/quality-gates.md §8 и docs/quality/gates.md:
//   version = фактический пин (mise.toml, package.json), а не версия из node_modules;
//   runs_in — известные шаги гейта или слоты хуков, иначе инструмент «висит в воздухе»;
//   шаг с полем tool обязан иметь запись в реестре, а blocking-инструмент — место запуска;
//   reviewed старше 180 дней — warn, а не тишина.
//
// Скрипт ничего не правит: только читает. Запуск — `npm run check:registry`
// или шаг registry-check внутри гейта.

import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { STEPS } from "./gate.mjs";

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const REGISTRY = path.join(ROOT, "docs/quality/tools.json");
const FRESH_DAYS = 180;
const HOOK_SLOTS = new Set(["pre-commit", "pre-push", "commit-msg", "prove-checks", "ci"]);
const KNOWN_STEPS = new Set(STEPS.map((step) => step.name));
const DATE_RE = /^\d{4}-\d{2}-\d{2}$/;

function reportOk(message) {
  console.log(`registry-check: ok — ${message}`);
}

function reportFail(message) {
  console.error(`registry-check: ${message}`);
}

function isValidDate(value) {
  if (typeof value !== "string" || !DATE_RE.test(value)) return false;
  const parsed = new Date(`${value}T00:00:00Z`);
  return !Number.isNaN(parsed.getTime()) && parsed.toISOString().slice(0, 10) === value;
}

function isStale(value) {
  return Date.now() - Date.parse(`${value}T00:00:00Z`) > FRESH_DAYS * 86_400_000;
}

/** Пины из TOML — по строке на ключ; закомментированный инструмент пином не считается. */
function tomlPins(text) {
  const pins = new Map();
  for (const line of text.split(/\r?\n/)) {
    if (/^\s*#/.test(line)) continue;
    const match = line.match(/^\s*"?([A-Za-z0-9_.:@/-]+)"?\s*=\s*"([^"]+)"/);
    if (match) pins.set(match[1], match[2]);
  }
  return pins;
}

function jsonPins(file) {
  const data = JSON.parse(fs.readFileSync(file, "utf8"));
  const pins = new Map();
  for (const key of ["dependencies", "devDependencies", "optionalDependencies"]) {
    for (const [name, version] of Object.entries(data[key] ?? {})) pins.set(name, version);
  }
  for (const [name, version] of Object.entries(data.engines ?? {})) pins.set(name, version);
  return pins;
}

/**
 * Фактический пин инструмента: ключ в TOML/JSON или regexp с одной группой
 * (для пинов вида `FROM python:3.14-slim`, который не является key=value).
 */
function actualPin(tool) {
  const pinFile = path.join(ROOT, tool.pinned_in);
  if (!fs.existsSync(pinFile)) return { problem: `pinned_in «${tool.pinned_in}» не существует` };

  if (typeof tool.pinned_pattern === "string" && tool.pinned_pattern.trim() !== "") {
    let pattern;
    try {
      pattern = new RegExp(tool.pinned_pattern, "m");
    } catch (error) {
      return { problem: `pinned_pattern не разбирается: ${error.message}` };
    }
    const match = pattern.exec(fs.readFileSync(pinFile, "utf8"));
    if (!match) return { problem: `pinned_pattern не найден в ${tool.pinned_in}` };
    if (!match[1])
      return { problem: `pinned_pattern в ${tool.pinned_in} не содержит группы захвата` };
    return { pin: match[1] };
  }

  const key = tool.pinned_as || tool.name;
  let pins;
  try {
    pins = pinFile.endsWith(".json")
      ? jsonPins(pinFile)
      : tomlPins(fs.readFileSync(pinFile, "utf8"));
  } catch (error) {
    return { problem: `${tool.pinned_in} не разбирается: ${error.message}` };
  }
  const pin = pins.get(key);
  if (pin === undefined) return { problem: `в ${tool.pinned_in} нет пина «${key}»` };
  return { pin };
}

function main() {
  if (!fs.existsSync(REGISTRY)) {
    reportFail("docs/quality/tools.json не найден");
    process.exit(1);
  }

  let registry;
  try {
    registry = JSON.parse(fs.readFileSync(REGISTRY, "utf8"));
  } catch (error) {
    reportFail(`tools.json не разбирается: ${error.message}`);
    process.exit(1);
  }

  const errors = [];
  const warns = [];

  if (!isValidDate(registry.reviewed)) {
    errors.push("tools.json: reviewed должен быть YYYY-MM-DD");
  } else if (isStale(registry.reviewed)) {
    warns.push(`tools.json: обзор старше ${FRESH_DAYS} дней (${registry.reviewed})`);
  }

  const tools = Array.isArray(registry.tools) ? registry.tools : [];
  if (tools.length === 0) errors.push("tools.json: пустой список tools");
  const seen = new Set();

  for (const tool of tools) {
    const label = tool.name || "(без имени)";
    if (!tool.name) {
      errors.push("tools.json: запись без name");
      continue;
    }
    if (seen.has(tool.name)) errors.push(`tools.json: дубликат инструмента ${tool.name}`);
    seen.add(tool.name);

    for (const field of ["version", "pinned_in", "source", "why"]) {
      if (typeof tool[field] !== "string" || tool[field].trim() === "") {
        errors.push(`${label}: пустое или отсутствующее поле ${field}`);
      }
    }
    if (typeof tool.blocking !== "boolean") {
      errors.push(`${label}: blocking должен быть true/false`);
    }
    if (!isValidDate(tool.reviewed)) {
      errors.push(`${label}: reviewed должен быть YYYY-MM-DD`);
    } else if (isStale(tool.reviewed)) {
      warns.push(`${label}: обзор старше ${FRESH_DAYS} дней (${tool.reviewed})`);
    }

    const runsIn = Array.isArray(tool.runs_in) ? tool.runs_in : [];
    if (runsIn.length === 0)
      errors.push(`${label}: пустой runs_in — инструмент нигде не запускается`);
    for (const slot of runsIn) {
      if (!KNOWN_STEPS.has(slot) && !HOOK_SLOTS.has(slot)) {
        errors.push(`${label}: неизвестное место запуска «${slot}»`);
      }
    }
    if (
      tool.blocking === true &&
      !runsIn.some((slot) => KNOWN_STEPS.has(slot) || HOOK_SLOTS.has(slot))
    ) {
      errors.push(`${label}: blocking, но ни шаг гейта, ни хук его не запускают`);
    }

    if (typeof tool.pinned_in !== "string" || tool.pinned_in.trim() === "") continue;
    const actual = actualPin(tool);
    if (actual.problem) {
      errors.push(`${label}: ${actual.problem}`);
    } else if (actual.pin !== tool.version) {
      errors.push(`${label}: version «${tool.version}» ≠ пин «${actual.pin}» в ${tool.pinned_in}`);
    }
  }

  // Обратная сторона: шаг, который объявляет инструмент, обязан иметь запись.
  for (const step of STEPS) {
    if (step.tool && !seen.has(step.tool)) {
      errors.push(`${step.name}: инструмент «${step.tool}» не описан в tools.json`);
    }
  }

  for (const warn of warns) console.warn(`registry-check: ! ${warn}`);
  if (errors.length) {
    for (const error of errors) reportFail(error);
    console.error("   исправьте docs/quality/tools.json или пины в mise.toml / package.json");
    process.exit(1);
  }
  reportOk(
    `${tools.length} инструментов сверены с пинами${warns.length ? `, ${warns.length} warn` : ""}`,
  );
}

main();
