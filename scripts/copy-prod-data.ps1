<#
.SYNOPSIS
  Разовый перенос данных Docker-прода в каталог данных заводской машины (ADR 0002, issue #7).

.DESCRIPTION
  Копирует SQLite БД и каталог images/ с прод-сервера в каталог данных
  заводской машины %LOCALAPPDATA%/Ekranchik/data:
    <DataDir>/ekranchik.db
    <DataDir>/images/

  Источник на сервере (см. docs/docker-prod-to-allinone-migration.md):
    <repo>/static/ekranchik.db  (контейнер: /app/static/ekranchik.db,
      infra/compose/docker-compose.prod.yml: volume ../../static:/app/static,
      environment DATABASE_URL=...////app/static/ekranchik.db)
    <repo>/static/images/       (контейнер: /app/static/images,
      environment IMAGES_DIR=/app/static/images)

  Проверки: источник БД и images/ существуют; целевой каталог создаётся;
  БД не копируется поверх запущенного процесса без -Force (ищем сервер
  EkranchikServer, висящий python-бэкенд по командной строке (-m uvicorn
  app.main:app + признаки localhost:8083/Ekranchik, чужой python не цепляем)
  и пробуем эксклюзивно открыть целевой файл БД).
  backend/.env скрипт никогда не копирует.

.EXAMPLE
  powershell -ExecutionPolicy Bypass -File scripts/copy-prod-data.ps1 -WhatIf
  # Сухой прогон с дефолтными путями (репозиторий + LOCALAPPDATA).

.EXAMPLE
  powershell -ExecutionPolicy Bypass -File scripts/copy-prod-data.ps1 `
    -SourceDb E:\prod\ekranchik.db -SourceImages E:\prod\images
  # Перенос с USB-носителя в %LOCALAPPDATA%/Ekranchik/data.
#>
[CmdletBinding(SupportsShouldProcess = $true)]
param(
  [string]$SourceDb = "",
  [string]$SourceImages = "",
  [string]$DataDir = (Join-Path $env:LOCALAPPDATA "Ekranchik/data"),
  [switch]$Force
)

$ErrorActionPreference = "Stop"

# Пути по умолчанию нельзя вычислить в param(): в Windows PowerShell 5.1 при
# [CmdletBinding] $PSScriptRoot в значениях по умолчанию пуст — поэтому
# вычисляем их здесь, где $PSScriptRoot уже доступен.
if ([string]::IsNullOrEmpty($SourceDb)) { $SourceDb = Join-Path $PSScriptRoot "../static/ekranchik.db" }
if ([string]::IsNullOrEmpty($SourceImages)) { $SourceImages = Join-Path $PSScriptRoot "../static/images" }

# --- 1. Источник существует ---
if (-not (Test-Path -LiteralPath $SourceDb -PathType Leaf)) {
  throw "Нет файла БД-источника: $SourceDb (сначала скопируйте static/ekranchik.db с прод-сервера)."
}
if (-not (Test-Path -LiteralPath $SourceImages -PathType Container)) {
  throw "Нет каталога images-источника: $SourceImages (сначала скопируйте static/images с прод-сервера)."
}

$TargetDb = Join-Path $DataDir "ekranchik.db"
$TargetImages = Join-Path $DataDir "images"

# --- 2. Цель не занята запущенным процессом (без -Force отказываем) ---
if (-not $Force) {
  # Живой сервер держит БД своим дочерним python-бэкендом. Имя процесса на
  # новых поставках — EkranchikServer (экран киоска Ekranchik БД не трогает,
  # поэтому в проверку не входит); EkranchikAllInOne оставлен для машин,
  # где ещё стоит прежняя поставка.
  $serverNames = @("EkranchikServer", "EkranchikAllInOne")
  $server = Get-Process -Name $serverNames -ErrorAction SilentlyContinue
  if ($server) {
    $names = ($server | ForEach-Object { "$($_.ProcessName) (PID $($_.Id))" }) -join ", "
    throw "Сервер Ekranchik запущен: $names. Закройте его (правый клик по значку в трее → «Выход») и повторите, либо -Force."
  }
  # Висящий python-бэкенд без лаунчера (см. ADR 0002): пакет запускает его как
  # python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8083.
  # Пара uvicorn+app.main сама по себе не уникальна (так называется entrypoint
  # любого FastAPI-проекта), поэтому требуем форму запуска -m uvicorn и один
  # из признаков нашего бэкенда: localhost / порт 8083 / путь Ekranchik.
  # Чужой python (venv другого проекта, системные скрипты) под фильтр не попадает.
  $backend = $null
  try {
    $backend = Get-CimInstance Win32_Process -Filter "Name='python.exe' OR Name='pythonw.exe' OR Name='uvicorn.exe'" -ErrorAction Stop |
      Where-Object {
        $_.CommandLine -match "-m\s+uvicorn" -and $_.CommandLine -match "app\.main" -and (
          $_.CommandLine -match "127\.0\.0\.1" -or
          $_.CommandLine -match "8083" -or
          $_.CommandLine -match "ekranchik"
        )
      }
  } catch {
    $backend = $null
  }
  if ($backend) {
    $backendPids = ($backend | Select-Object -ExpandProperty ProcessId) -join ", "
    throw "Бэкенд python/uvicorn запущен отдельно (PID $backendPids, app.main). Закройте сервер Ekranchik (значок в трее → «Выход») и повторите, либо -Force."
  }
  if (Test-Path -LiteralPath $TargetDb -PathType Leaf) {
    try {
      $fs = [System.IO.File]::Open($TargetDb, "Open", "ReadWrite", "None")
      $fs.Close()
    } catch {
      throw "Целевая БД занята (похоже, сервер запущен): $TargetDb. Закройте сервер Ekranchik и повторите, либо -Force."
    }
  }
}

# --- 3. Копирование + проверка результата (внутри ShouldProcess, чтобы -WhatIf был сухим) ---
if ($PSCmdlet.ShouldProcess($DataDir, "Разложить данные прод-сервера (ekranchik.db + images/)")) {
  New-Item -ItemType Directory -Force -Path $DataDir, $TargetImages | Out-Null
  Copy-Item -LiteralPath $SourceDb -Destination $TargetDb -Force
  Copy-Item -Path (Join-Path $SourceImages "*") -Destination $TargetImages -Recurse -Force
  if (-not (Test-Path -LiteralPath $TargetDb -PathType Leaf)) {
    throw "Копирование не удалось: нет $TargetDb."
  }
  $srcCount = (Get-ChildItem -LiteralPath $SourceImages -Recurse -File | Measure-Object).Count
  $dstCount = (Get-ChildItem -LiteralPath $TargetImages -Recurse -File | Measure-Object).Count
  if ($dstCount -lt $srcCount) {
    throw "Копирование неполное: источник файлов $srcCount, цель $dstCount."
  }
  Write-Host "==> Готово: $TargetDb + $dstCount файлов в images/."
  Write-Host "    Дальнейшей синхронизации с продом нет — машины живут независимо."
}
