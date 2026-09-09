; EkranchikSetup — один установщик, два типа установки (issue #6).
;
;   «Только киоск» — состав байт-в-байт как раньше (секция [Files] с
;     Components: kiosk повторяет эталонный установщик киоска).
;   «Полный пакет» — киоск + AllInOne + embedded Python + backend + frontend/dist.
;
; Повторный запуск меняет тип: доустановка докачивает компонент full,
; удаление типа (full -> kiosk) стирает файлы компонента full секцией
; [InstallDelete]. Каталог данных и живые настройки
; (%LOCALAPPDATA%\Ekranchik: data/, *.json, logs/) установкой, обновлением
; и удалением компонентов НЕ затрагиваются — они нигде ниже не перечислены.
;
; Сборка пакета перед компиляцией (порядок важен):
;   1. Киоск:        рядом с этим файлом должен лежать Ekranchik.exe
;                    (+ WebView2Loader.dll, runtimes/, idle_clock.html,
;                     kiosk_config.json, ktm_colored.png, launcher.ico) —
;                    как раньше.
;   2. AllInOne:     опубликовать self-contained и положить рядом с этим
;                    файлом EkranchikAllInOne.exe, например:
;                    dotnet publish source_code\EkranchikAllInOne\EkranchikAllInOne.csproj -c Release -r win-x64 --self-contained -p:PublishSingleFile=true
;                    (если публикация НЕ single-file — рядом также кладутся
;                    EkranchikAllInOne.dll/.deps.json/.runtimeconfig.json,
;                    ниже они подключены с skipifsourcedoesntexist).
;   3. Python-пакет: powershell -ExecutionPolicy Bypass -File ..\scripts\build-full-package.ps1
;                    (раскладывает ..\dist-full\{python,backend,dist}).
;
; Компиляция: ISCC.exe launcher.iss (Inno Setup 6).
; Песочница без компилятора: структурная валидация — каждый Source секции
; [Files] существует на диске после шагов 1–3 (python/ и AllInOne.exe —
; артефакты полной сборки, в сухом прогоне отсутствуют штатно).

#define MyAppName "Ekranchik"
#define MyAppPublisher "Mavka"
#define MyAppExeName "Ekranchik.exe"
#define MyAppAllInOneExeName "EkranchikAllInOne.exe"
#define MyAppIconName "launcher.ico"

#ifndef MyAppVersion
  #define MyAppVersion "1.0.3"
#endif

[Setup]
AppId={{C6D2B1C1-827A-4D3F-B5FE-D372FEBF44C7}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={localappdata}\{#MyAppName}
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
OutputDir=Output
OutputBaseFilename=EkranchikSetup
SetupIconFile={#MyAppIconName}
Compression=lzma
SolidCompression=yes
WizardStyle=modern
PrivilegesRequired=lowest
DisableDirPage=no

[Languages]
Name: "russian"; MessagesFile: "compiler:Languages\Russian.isl"

[Types]
Name: "kiosk"; Description: "Только киоск (как раньше)"
Name: "full"; Description: "Полный пакет: киоск + сервер + Python + веб-интерфейс"
Name: "custom"; Description: "Выборочная установка"; Flags: iscustom

[Components]
Name: "kiosk"; Description: "Киоск Ekranchik (обязательный компонент)"; Types: kiosk full custom; Flags: fixed
Name: "full"; Description: "Сервер, embedded Python и веб-интерфейс"; Types: full

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[Files]
; --- Компонент «kiosk»: состав эталона, ничего не убрано и не добавлено. ---
; kiosk_config.json ставится только на чистую установку (onlyifdoesntexist):
; установщик одновременно кладёт seed по умолчанию и НЕ затирает живые
; настройки пользователя при обновлении/переустановке/смене типа.
Source: "Ekranchik.exe"; DestDir: "{app}"; Flags: ignoreversion; Components: kiosk
Source: "WebView2Loader.dll"; DestDir: "{app}"; Flags: ignoreversion; Components: kiosk
Source: "runtimes\*"; DestDir: "{app}\runtimes"; Flags: ignoreversion recursesubdirs createallsubdirs; Components: kiosk
Source: "idle_clock.html"; DestDir: "{app}"; Flags: ignoreversion; Components: kiosk
Source: "kiosk_config.json"; DestDir: "{app}"; Flags: ignoreversion onlyifdoesntexist; Components: kiosk
Source: "ktm_colored.png"; DestDir: "{app}"; Flags: ignoreversion; Components: kiosk
Source: "launcher.ico"; DestDir: "{app}"; Flags: ignoreversion; Components: kiosk
; --- Компонент «full»: раскладка рядом с exe (контракт ADR 0002/issue #5). ---
; AllInOne ищет backend/ рядом с собой, киоск — Ekranchik.exe рядом с собой.
Source: "{#MyAppAllInOneExeName}"; DestDir: "{app}"; Flags: ignoreversion; Components: full
Source: "EkranchikAllInOne.dll"; DestDir: "{app}"; Flags: ignoreversion skipifsourcedoesntexist; Components: full
Source: "EkranchikAllInOne.deps.json"; DestDir: "{app}"; Flags: ignoreversion skipifsourcedoesntexist; Components: full
Source: "EkranchikAllInOne.runtimeconfig.json"; DestDir: "{app}"; Flags: ignoreversion skipifsourcedoesntexist; Components: full
Source: "..\dist-full\backend\*"; DestDir: "{app}\backend"; Flags: ignoreversion recursesubdirs createallsubdirs; Components: full
Source: "..\dist-full\dist\*"; DestDir: "{app}\dist"; Flags: ignoreversion recursesubdirs createallsubdirs; Components: full
Source: "..\dist-full\python\*"; DestDir: "{app}\python"; Flags: ignoreversion recursesubdirs createallsubdirs; Components: full

[InstallDelete]
; Смена типа full -> kiosk (и выборочная без full): стереть файлы компонента
; full. data/, *.json, logs/ здесь намеренно отсутствуют — данные и настройки
; переживают удаление компонентов. На чистой установке удалять нечего (no-op).
Type: files; Name: "{app}\{#MyAppAllInOneExeName}"; Check: not IsFullSelected
Type: files; Name: "{app}\EkranchikAllInOne.dll"; Check: not IsFullSelected
Type: files; Name: "{app}\EkranchikAllInOne.deps.json"; Check: not IsFullSelected
Type: files; Name: "{app}\EkranchikAllInOne.runtimeconfig.json"; Check: not IsFullSelected
Type: filesandordirs; Name: "{app}\backend"; Check: not IsFullSelected
Type: filesandordirs; Name: "{app}\dist"; Check: not IsFullSelected
Type: filesandordirs; Name: "{app}\python"; Check: not IsFullSelected
Type: files; Name: "{group}\{#MyAppName} Полный пакет.lnk"; Check: not IsFullSelected
Type: files; Name: "{userdesktop}\{#MyAppName} Полный пакет.lnk"; Check: not IsFullSelected

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; IconFilename: "{app}\{#MyAppIconName}"; Components: kiosk
Name: "{userdesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; IconFilename: "{app}\{#MyAppIconName}"; Tasks: desktopicon; Components: kiosk
Name: "{group}\{#MyAppName} Полный пакет"; Filename: "{app}\{#MyAppAllInOneExeName}"; IconFilename: "{app}\{#MyAppIconName}"; Components: full
Name: "{userdesktop}\{#MyAppName} Полный пакет"; Filename: "{app}\{#MyAppAllInOneExeName}"; IconFilename: "{app}\{#MyAppIconName}"; Tasks: desktopicon; Components: full

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "{cm:LaunchProgram,{#StringChange(MyAppName, '&', '&&')}}"; Flags: nowait postinstall skipifsilent; Check: not IsFullSelected
Filename: "{app}\{#MyAppAllInOneExeName}"; Description: "Запустить Ekranchik (полный пакет)"; Flags: nowait postinstall skipifsilent; Components: full

[Code]
function IsFullSelected(): Boolean;
begin
  Result := WizardIsComponentSelected('full');
end;
