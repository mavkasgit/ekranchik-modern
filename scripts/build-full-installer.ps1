<#
.SYNOPSIS
  Сборка полного установщика EkranchikSetup.exe одним запуском (issue #8).

.DESCRIPTION
  Оркестратор: launcher/launcher.iss (issue #04 — два приложения в одном
  установщике) + scripts/build-full-package.ps1. Шаги по порядку:
    1. frontend: npm ci + npm run build  -> frontend/dist (бэкенд раздаёт его сам)
    2. пакет:    scripts/build-full-package.ps1 -> dist-full/{python,backend,dist}
    3. киоск:    ТОЛЬКО проверка (Ekranchik.exe + файлы эталона рядом с .iss);
                 сборка киоска — ручной релизный процесс киоска, см. -BuildKiosk
    4. сервер:   dotnet publish -> launcher/EkranchikServer.exe (команда из шапки .iss)
    5. установщик: ISCC.exe launcher.iss -> launcher/Output/EkranchikSetup.exe

  Установщик ставит либо экран (Ekranchik.exe + загрузчик WebView2; сам рантайм
  Microsoft Edge WebView2 он ставит на машине, где рантайма ещё нет), либо
  сервер (EkranchikServer.exe + встроенный Python/бэкенд/веб-интерфейс), либо
  оба. Ни одного ручного шага сборки рантайм не добавляет: он скачивается на
  машине при установке (нет сети — установка не падает, см. launcher.iss).

  СХЕМА ВЕРСИЙ (без конфликтов с релизами киоска):
    киоск:          теги v*             + ассет Ekranchik.exe        (ручной процесс, не трогать)
    полный установщик: теги full-v*     + ассет EkranchikSetup.exe   (этот скрипт + workflow рядом)
  Префиксы тегов и имена ассетов не пересекаются. -Version переопределяет
  #define MyAppVersion из .iss при компиляции (ключ ISCC /DMyAppVersion=).

  Песочница без ISCC: без -SkipIscc скрипт падает с понятной инструкцией
  (шаг 5). С -SkipIscc вместо компиляции — структурная валидация секции
  [Files]: файлы киоска строго, артефакты сервера (EkranchikServer.exe,
  dist-full) — предупреждение, т.к. в сухом прогоне отсутствуют штатно.

.EXAMPLE
  powershell -ExecutionPolicy Bypass -File scripts/build-full-installer.ps1 -SkipPythonDownload
  # Полная локальная сборка (embedded Python скачивается, ~сотни МБ).

.EXAMPLE
  powershell -ExecutionPolicy Bypass -File scripts/build-full-installer.ps1 `
    -SkipFrontendBuild -SkipPythonDownload -SkipDotnetPublish -SkipIscc -AllowMissingDist
  # Сухой прогон оркестрации без сети и компилятора.

.EXAMPLE
  powershell -ExecutionPolicy Bypass -File scripts/build-full-installer.ps1 -Version 1.0.4
  # Переопределить версию установщика (CI делает так из тега full-v1.0.4).
#>
[CmdletBinding()]
param(
  [string]$Version = "",
  [string]$Configuration = "Release",
  [switch]$SkipFrontendBuild,
  [switch]$SkipPythonDownload,
  [switch]$SkipDotnetPublish,
  [switch]$SkipIscc,
  [switch]$AllowMissingDist,
  [switch]$BuildKiosk
)

$ErrorActionPreference = "Stop"
$Root         = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$LauncherDir  = Join-Path $Root "launcher"
$IssPath      = Join-Path $LauncherDir "launcher.iss"
$FrontendDir  = Join-Path $Root "frontend"
$FrontendDist = Join-Path $FrontendDir "dist"
$KioskProj    = Join-Path $Root "launcher/source_code/EkranchikKiosk.csproj"
$ServerProj   = Join-Path $Root "launcher/source_code/EkranchikServer/EkranchikServer.csproj"
function Join2([string]$a, [string]$b) { Join-Path $a $b }

if (-not (Test-Path $IssPath)) { throw "Не найден $IssPath (база #6 обязательна)." }

# --- Версия: единый источник — корневой VERSION (-Version переопределяет) ---
if ([string]::IsNullOrWhiteSpace($Version)) {
  $versionFile = Join2 $Root "VERSION"
  if (Test-Path $versionFile) { $Version = ((Get-Content -LiteralPath $versionFile -Raw).Trim() -split '\s+')[0] }
}
if ([string]::IsNullOrWhiteSpace($Version)) { throw "Не удалось определить версию (корневой VERSION отсутствует и -Version не задан)." }
Write-Host "==> Версия установщика: $Version"

# --- 1. Frontend ---
if ($SkipFrontendBuild) {
  Write-Host "==> -SkipFrontendBuild: пропускаю npm-сборку."
} else {
  Write-Host "==> Собираю frontend"
  if (-not (Test-Path (Join2 $FrontendDir "package.json"))) { throw "Не найден $FrontendDir/package.json." }
  Push-Location $FrontendDir
  try {
    & npm ci
    if ($LASTEXITCODE -ne 0) { throw "npm ci завершился с кодом $LASTEXITCODE." }
    & npm run build
    if ($LASTEXITCODE -ne 0) { throw "npm run build завершился с кодом $LASTEXITCODE." }
  } finally { Pop-Location }
}
if (-not (Test-Path (Join2 $FrontendDist "index.html"))) {
  $msg = "Нет $FrontendDist/index.html — frontend не собран."
  if ($AllowMissingDist) { Write-Warning "$msg Продолжаю (флаг -AllowMissingDist)." }
  else { throw "$msg Соберите (шаг 1) или передайте -AllowMissingDist." }
}

# --- 2. Пакет заводской машины (issue #5) ---
Write-Host "==> Собираю пакет scripts/build-full-package.ps1"
$pkgArgs = @{}
if ($SkipPythonDownload) { $pkgArgs["SkipPythonDownload"] = $true }
if ($AllowMissingDist)   { $pkgArgs["AllowMissingDist"] = $true }
& (Join2 $Root "scripts/build-full-package.ps1") @pkgArgs
if (-not $?) { throw "build-full-package.ps1 завершился с ошибкой." }

# --- 3. Киоск: проверка эталона (состав файлов — см. [Files] Components: kiosk) ---
# Ручной релиз киоска — эталон, этот скрипт его не пересобирает (кроме -BuildKiosk для CI).
if ($BuildKiosk) {
  Write-Host "==> -BuildKiosk: публикую киоск из исходников"
  $tmp = Join2 $LauncherDir "publish-kiosk-tmp"
  if (Test-Path $tmp) { Remove-Item $tmp -Recurse -Force }
  & dotnet publish $KioskProj -c $Configuration -r win-x64 --self-contained "-p:PublishSingleFile=true" "-p:Version=$Version" -o $tmp
  if ($LASTEXITCODE -ne 0) { throw "dotnet publish киоска завершился с кодом $LASTEXITCODE." }
  Copy-Item -LiteralPath (Join2 $tmp "Ekranchik.exe") -Destination $LauncherDir -Force
  Copy-Item -LiteralPath (Join2 $tmp "WebView2Loader.dll") -Destination $LauncherDir -Force
  Copy-Item -LiteralPath (Join2 $tmp "runtimes") -Destination $LauncherDir -Recurse -Force
  Remove-Item $tmp -Recurse -Force
  if (-not (Test-Path (Join2 $LauncherDir "kiosk_config.json"))) {
    # seed по умолчанию (репозиторий его не хранит: kiosk_config.json в .gitignore).
    # Seed совпадает с тем, что приложение само пишет в пустой конфиг: адрес
    # дашборда с портом 8083 из глоссария (CONTEXT.md, «Адрес для экранов»),
    # монитор 0, оба признака выключены. Оба признака выключены не просто так —
    # с включённым auto_launch_on_second_monitor окно настроек на двух
    # мониторах не показывается, и оператор не попадёт в настройки.
    Write-Host "kiosk_config.json отсутствует — кладу seed по умолчанию (onlyifdoesntexist в .iss не затрет живой)."
    Set-Content -LiteralPath (Join2 $LauncherDir "kiosk_config.json") -Encoding UTF8 -Value @'
{
    "url": "http://localhost:8083",
    "monitor": 0,
    "auto_launch_on_second_monitor": false,
    "windows_startup": false
}
'@
  }
}
$kioskFiles = @("Ekranchik.exe", "WebView2Loader.dll", "runtimes", "idle_clock.html", "kiosk_config.json", "ktm_colored.png", "launcher.ico")
foreach ($f in $kioskFiles) {
  if (-not (Test-Path (Join2 $LauncherDir $f))) {
    throw "Нет $f рядом с launcher.iss. Соберите киоск его штатным процессом (dotnet publish source_code/EkranchikKiosk.csproj) или передайте -BuildKiosk."
  }
}
Write-Host "==> Киоск-эталон на месте."

# --- 4. Публикация сервера (команда из шапки .iss) ---
$ServerExe = Join2 $LauncherDir "EkranchikServer.exe"
if ($SkipDotnetPublish) {
  Write-Host "==> -SkipDotnetPublish: пропускаю dotnet publish сервера."
} else {
  Write-Host "==> Публикую сервер"
  $tmp = Join2 $LauncherDir "publish-server-tmp"
  if (Test-Path $tmp) { Remove-Item $tmp -Recurse -Force }
  & dotnet publish $ServerProj -c $Configuration -r win-x64 --self-contained "-p:PublishSingleFile=true" "-p:Version=$Version" -o $tmp
  if ($LASTEXITCODE -ne 0) { throw "dotnet publish сервера завершился с кодом $LASTEXITCODE." }
  Copy-Item -LiteralPath (Join2 $tmp "EkranchikServer.exe") -Destination $LauncherDir -Force
  foreach ($sidecar in @("EkranchikServer.dll", "EkranchikServer.deps.json", "EkranchikServer.runtimeconfig.json")) {
    if (Test-Path (Join2 $tmp $sidecar)) { Copy-Item -LiteralPath (Join2 $tmp $sidecar) -Destination $LauncherDir -Force }
  }
  Remove-Item $tmp -Recurse -Force
}
if (-not (Test-Path $ServerExe)) {
  Write-Warning "Нет EkranchikServer.exe — в сухом прогоне штатно, для установщика обязателен (шаг 4 или уберите -SkipDotnetPublish)."
}

# --- 5. ISCC ---
function Find-Iscc {
  $cmd = Get-Command ISCC.exe -ErrorAction SilentlyContinue
  if ($cmd) { return $cmd.Source }
  foreach ($p in @("$env:ProgramFiles\Inno Setup 6\ISCC.exe", "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe",
                   "$env:LOCALAPPDATA\Programs\Inno Setup 6\ISCC.exe")) {
    if ($p -and (Test-Path $p)) { return $p }
  }
  return $null
}
$Iscc = Find-Iscc
if ($SkipIscc) {
  Write-Host "==> -SkipIscc: структурная валидация [Files] вместо компиляции."
  $defines = @{}
  foreach ($dl in (Get-Content -LiteralPath $IssPath)) {
    if ($dl -match '^\s*#define\s+(\w+)\s+"([^"]+)"') { $defines[$Matches[1]] = $Matches[2] }
  }
  $fail = $false
  $inFiles = $false
  foreach ($line in (Get-Content -LiteralPath $IssPath)) {
    if ($line -match '^\s*\[(.+)\]\s*$') { $inFiles = ($Matches[1] -eq "Files"); continue }
    if (-not $inFiles) { continue }
    if ($line -match '^\s*Source:\s*"([^"]+)"\s*;(.*)$') {
      $src, $rest = $Matches[1], $Matches[2]
      if ($src -like "compiler:*") { continue }
      foreach ($k in $defines.Keys) { $src = $src -replace "\{#$k\}", $defines[$k] }
      $src = $src -replace '[\\/]\*$', ''
      $full = Join-Path $LauncherDir ($src -replace '/', '\')
      $isServer = $rest -match 'Components:\s*server'
      $optional = $rest -match 'skipifsourcedoesntexist'
      $exists = Test-Path $full
      if (-not $exists -and -not $optional) {
        if ($isServer) { Write-Warning "Отсутствует (сервер, сухой прогон штатно): $src" }
        else { Write-Host "ОТСУТСТВУЕТ (киоск, ошибка): $src"; $fail = $true }
      }
    }
  }
  if ($fail) { throw "Валидация [Files] не прошла: отсутствуют обязательные файлы киоска." }
  Write-Host "==> Валидация прошла."
} elseif (-not $Iscc) {
  throw "ISCC.exe не найден. Установите Inno Setup 6 (https://jrsoftware.org/isdl.php, или winget/choco: 'choco install innosetup') и повторите. Для сухого прогона без компилятора добавьте -SkipIscc."
} else {
  Write-Host "==> Компилирую установщик ($Iscc)"
  & $Iscc "/DMyAppVersion=$Version" $IssPath
  if ($LASTEXITCODE -ne 0) { throw "ISCC завершился с кодом $LASTEXITCODE." }
  $setup = Join2 $LauncherDir "Output/EkranchikSetup-$Version.exe"
  if (-not (Test-Path $setup)) { throw "ISCC отработал, но $setup не создан." }
  Write-Host "==> Готово: $setup"
}
