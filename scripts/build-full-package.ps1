<#
.SYNOPSIS
  Сборка самодостаточного пакета заводской машины (ADR 0002, issue #5).

.DESCRIPTION
  Одним запуском раскладывает в папку дистрибутива:
    <OutDir>/python/   — embedded Python 3.12 (+ pip + зависимости бэкенда)
    <OutDir>/backend/  — код бэкенда (app/, alembic/, alembic.ini, requirements.txt)
    <OutDir>/dist/     — собранный frontend/dist (бэкенд раздаёт его сам на 8083)

  ПРАВИЛО СОХРАННОСТИ ДАННЫХ: скрипт НИКОГДА не создаёт, не копирует и не
  удаляет каталог data/ внутри пакета. Данные живут только в
  %LOCALAPPDATA%/Ekranchik/data и переживают повторную сборку/установку.
  При очистке <OutDir> случайно оказавшийся там data/ сохраняется, всё
  остальное удаляется.

  backend/.env НИКОГДА не копируется в пакет (dev-значения не должны утечь
  в прод; в пакете действуют дефолты config.py → LOCALAPPDATA).

.EXAMPLE
  powershell -ExecutionPolicy Bypass -File scripts/build-full-package.ps1 -SkipPythonDownload
  # Сухой прогон структуры без скачивания (~сотни МБ) и pip install.

.EXAMPLE
  powershell -ExecutionPolicy Bypass -File scripts/build-full-package.ps1
  # Полная сборка: embedded Python + зависимости + код + dist.
#>
[CmdletBinding()]
param(
  [string]$OutDir = "",
  [string]$PythonVersion = "3.12.10",
  [switch]$SkipPythonDownload,
  [switch]$AllowMissingDist
)

$ErrorActionPreference = "Stop"
$Root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
if ([string]::IsNullOrWhiteSpace($OutDir)) { $OutDir = Join-Path $Root "dist-full" }

$PythonDir  = Join-Path $OutDir "python"
$BackendDir = Join-Path $OutDir "backend"
$DistDir    = Join-Path $OutDir "dist"
$DataDir    = Join-Path $OutDir "data"   # запретная зона, см. правило выше
function Join2([string]$a, [string]$b) { Join-Path $a $b }

# --- 0. Подготовка каталога: чистим всё, КРОМЕ data/ (сохранность данных) ---
$DataExisted = Test-Path $DataDir
if ($DataExisted) {
  Write-Warning "Обнаружен $DataDir — НЕ ТРОГАЮ (правило сохранности данных)."
}
New-Item -ItemType Directory -Force -Path $OutDir | Out-Null
Get-ChildItem -LiteralPath $OutDir -Force | Where-Object { $_.FullName -ne $DataDir } | Remove-Item -Recurse -Force
New-Item -ItemType Directory -Force -Path $PythonDir, $BackendDir, $DistDir | Out-Null

# --- 1. Embedded Python ---
if ($SkipPythonDownload) {
  Write-Host "==> -SkipPythonDownload: пропускаю скачивание embedded Python (сухой прогон)."
} else {
  $ver = $PythonVersion -split "\."
  $mm = $ver[0] + $ver[1]  # "3.12.10" -> "312"
  $zipUrl = "https://www.python.org/ftp/python/$PythonVersion/python-$PythonVersion-embed-amd64.zip"
  $zipPath = Join2 ([IO.Path]::GetTempPath()) "ekranchik-python-embed-$PythonVersion.zip"
  Write-Host "==> Скачиваю $zipUrl"
  Invoke-WebRequest -Uri $zipUrl -OutFile $zipPath
  Write-Host "==> Распаковываю в $PythonDir"
  Expand-Archive -LiteralPath $zipPath -DestinationPath $PythonDir -Force
  Remove-Item -LiteralPath $zipPath -Force

  # Разрешить site-packages (иначе pip-зависимости не подхватятся).
  $pth = Join2 $PythonDir "python$mm._pth"
  if (Test-Path $pth) {
    (Get-Content -LiteralPath $pth) -replace "^#\s*import site", "import site" |
      Set-Content -LiteralPath $pth -Encoding Ascii
    Write-Host "==> Включён 'import site' в python$mm._pth"
  } else {
    throw "Не найден python$mm._pth — проверьте -PythonVersion."
  }

  # pip для embedded-дистрибутива.
  $getPip = Join2 ([IO.Path]::GetTempPath()) "ekranchik-get-pip.py"
  Write-Host "==> Ставлю pip (get-pip.py)"
  Invoke-WebRequest -Uri "https://bootstrap.pypa.io/get-pip.py" -OutFile $getPip
  & (Join2 $PythonDir "python.exe") $getPip --no-warn-script-location
  Remove-Item -LiteralPath $getPip -Force

  # Зависимости бэкенда в embedded Python.
  $req = Join2 (Join2 $Root "backend") "requirements.txt"
  Write-Host "==> Ставлю зависимости из backend/requirements.txt"
  & (Join2 $PythonDir "python.exe") -m pip install --no-warn-script-location -r $req
}

# --- 2. Код бэкенда (без .env, кэшей и тестов) ---
Write-Host "==> Копирую бэкенд"
$BackendSrc = Join2 $Root "backend"
Copy-Item -LiteralPath (Join2 $BackendSrc "app") -Destination (Join2 $BackendDir "app") -Recurse -Force
Copy-Item -LiteralPath (Join2 $BackendSrc "alembic") -Destination (Join2 $BackendDir "alembic") -Recurse -Force
Copy-Item -LiteralPath (Join2 $BackendSrc "alembic.ini") -Destination (Join2 $BackendDir "alembic.ini") -Force
Copy-Item -LiteralPath (Join2 $BackendSrc "requirements.txt") -Destination (Join2 $BackendDir "requirements.txt") -Force
Write-Host "==> Кладу VERSION (единый источник версии для рантайма бэкенда)"
$VersionSrc = Join2 $Root "VERSION"
if (Test-Path $VersionSrc) {
  Copy-Item -LiteralPath $VersionSrc -Destination (Join2 $BackendDir "VERSION") -Force
  Copy-Item -LiteralPath $VersionSrc -Destination (Join-Path $OutDir "VERSION") -Force
} else {
  Write-Warning "Корневой VERSION не найден — бэкенд в пакете отдаст фолбэк 'dev'."
}
Get-ChildItem -LiteralPath $BackendDir -Recurse -Force -Directory |
  Where-Object { $_.Name -eq "__pycache__" -or $_.Name -eq ".pytest_cache" } |
  Remove-Item -Recurse -Force
if (Test-Path (Join2 $BackendDir ".env")) {
  throw "Запрещено: backend/.env попал в пакет (dev-конфиг не должен утечь в прод)."
}

# --- 3. Собранный фронтенд ---
Write-Host "==> Копирую frontend/dist"
$FrontendDist = Join2 (Join2 $Root "frontend") "dist"
if (-not (Test-Path (Join2 $FrontendDist "index.html"))) {
  if ($AllowMissingDist) {
    Write-Warning "frontend/dist без index.html — пропускаю (флаг -AllowMissingDist)."
  } else {
    throw "frontend/dist не собран (нет index.html). Соберите фронтенд или используйте -AllowMissingDist."
  }
} else {
  Copy-Item -Path (Join2 $FrontendDist "*") -Destination $DistDir -Recurse -Force
}

# --- 4. Финальные проверки ---
if ((Test-Path $DataDir) -and (-not $DataExisted)) {
  throw "Запрещено: сборка создала data/ — так быть не должно."
}
if ($DataExisted) {
  Write-Warning "data/ сохранён нетронутым (правило сохранности данных)."
}
Write-Host "==> Готово. Структура пакета:"
Get-ChildItem -LiteralPath $OutDir | ForEach-Object { Write-Host ("    " + $_.Name + "/") }
Write-Host "    Запуск на целевой машине: python/python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8083  (CWD = backend/)"
