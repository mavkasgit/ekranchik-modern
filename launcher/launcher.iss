; EkranchikSetup — один установщик, два типа установки (issue #6, #9).
;
;   «Только киоск» — состав байт-в-байт как раньше: экран отдельным
;     процессом (Ekranchik.exe + WebView2 + конфиги).
;   «Полный пакет» — ОДНО приложение EkranchikAllInOne.exe: сервер, экран
;     киоска, трей и настройки в одном процессе (issue #9)
;     + embedded Python + backend + frontend/dist.
;
; Повторный запуск меняет тип: переход full -> kiosk стирает файлы
; компонента full, переход kiosk -> full стирает отдельный киоск exe —
; секцией [InstallDelete]. Каталог данных и живые настройки
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
;                    dotnet publish source_code\EkranchikAllInOne\EkranchikAllInOne.csproj -c Release -r win-x64 --self-contained -p:PublishSingleFile=true "-p:Version=$(Get-Content ..\VERSION)"
;                    (штамп из корневого VERSION; без флага версия подхватится
;                    сама через source_code\Directory.Build.props).
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
OutputBaseFilename=EkranchikSetup-{#MyAppVersion}
SetupIconFile={#MyAppIconName}
Compression=lzma
SolidCompression=yes
WizardStyle=modern
PrivilegesRequired=lowest
DisableDirPage=no
; Апгрейд-путь: каталог, тип установки (kiosk/full) и задачи наследуются
; от предыдущей установки с тем же AppId — тип full не сбрасывается молча.
UsePreviousAppDir=yes
UsePreviousSetupType=yes
UsePreviousTasks=yes

[Languages]
Name: "russian"; MessagesFile: "compiler:Languages\Russian.isl"

[Types]
Name: "kiosk"; Description: "Только киоск (как раньше)"
Name: "full"; Description: "Полный пакет: одно приложение — сервер + киоск + Python + веб-интерфейс"
Name: "custom"; Description: "Выборочная установка"; Flags: iscustom

[Components]
Name: "runtime"; Description: "Общие файлы (WebView2, конфиг, иконки)"; Types: kiosk full custom; Flags: fixed
Name: "kioskapp"; Description: "Киоск Ekranchik (только экран, отдельный exe)"; Types: kiosk
Name: "full"; Description: "Сервер, embedded Python и веб-интерфейс + экран в одном приложении"; Types: full

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[Files]
; --- Компонент «runtime»: общие файлы обоих режимов. ---
; kiosk_config.json ставится только на чистую установку (onlyifdoesntexist):
; установщик одновременно кладёт seed по умолчанию и НЕ затирает живые
; настройки пользователя при обновлении/переустановке/смене типа.
Source: "WebView2Loader.dll"; DestDir: "{app}"; Flags: ignoreversion; Components: runtime
Source: "runtimes\*"; DestDir: "{app}\runtimes"; Flags: ignoreversion recursesubdirs createallsubdirs; Components: runtime
Source: "idle_clock.html"; DestDir: "{app}"; Flags: ignoreversion; Components: runtime
Source: "kiosk_config.json"; DestDir: "{app}"; Flags: ignoreversion onlyifdoesntexist; Components: runtime
Source: "ktm_colored.png"; DestDir: "{app}"; Flags: ignoreversion; Components: runtime
Source: "launcher.ico"; DestDir: "{app}"; Flags: ignoreversion; Components: runtime
; --- Компонент «kioskapp»: самостоятельный киоск-процесс («Только киоск»). ---
Source: "Ekranchik.exe"; DestDir: "{app}"; Flags: ignoreversion; Components: kioskapp
; --- Компонент «full»: ОДНО приложение — merged exe с экраном киоска
; внутри (issue #9), плюс раскладка рядом (контракт ADR 0002/issue #5):
; AllInOne ищет backend/ рядом с собой. ---
Source: "{#MyAppAllInOneExeName}"; DestDir: "{app}"; Flags: ignoreversion; Components: full
Source: "EkranchikAllInOne.dll"; DestDir: "{app}"; Flags: ignoreversion skipifsourcedoesntexist; Components: full
Source: "EkranchikAllInOne.deps.json"; DestDir: "{app}"; Flags: ignoreversion skipifsourcedoesntexist; Components: full
Source: "EkranchikAllInOne.runtimeconfig.json"; DestDir: "{app}"; Flags: ignoreversion skipifsourcedoesntexist; Components: full
Source: "..\dist-full\backend\*"; DestDir: "{app}\backend"; Flags: ignoreversion recursesubdirs createallsubdirs; Components: full
Source: "..\dist-full\dist\*"; DestDir: "{app}\dist"; Flags: ignoreversion recursesubdirs createallsubdirs; Components: full
Source: "..\dist-full\python\*"; DestDir: "{app}\python"; Flags: ignoreversion recursesubdirs createallsubdirs; Components: full

[InstallDelete]
; Смена типа full -> kiosk (и выборочная без full): стереть merged exe и
; серверную раскладку. Переход kiosk -> full: отдельный киоск-процесс
; больше не ставится — его место занимает merged exe (issue #9).
; data/, *.json, logs/ здесь намеренно отсутствуют — данные и настройки
; переживают удаление компонентов. На чистой установке удалять нечего.
Type: files; Name: "{app}\{#MyAppAllInOneExeName}"; Check: not IsFullSelected
Type: files; Name: "{app}\EkranchikAllInOne.dll"; Check: not IsFullSelected
Type: files; Name: "{app}\EkranchikAllInOne.deps.json"; Check: not IsFullSelected
Type: files; Name: "{app}\EkranchikAllInOne.runtimeconfig.json"; Check: not IsFullSelected
Type: filesandordirs; Name: "{app}\backend"; Check: not IsFullSelected
Type: filesandordirs; Name: "{app}\dist"; Check: not IsFullSelected
Type: filesandordirs; Name: "{app}\python"; Check: not IsFullSelected
Type: files; Name: "{group}\{#MyAppName} Полный пакет.lnk"
Type: files; Name: "{userdesktop}\{#MyAppName} Полный пакет.lnk"
; Старая десктоп-иконка «Ekranchik» указывала на киоск exe — на full она
; пересоздаётся [Icons] только при отмеченной задаче, а старый exe удаляется
; выше: битую иконку стираем до возможной пересоздания.
Type: files; Name: "{userdesktop}\{#MyAppName}.lnk"; Check: IsFullSelected
Type: files; Name: "{app}\{#MyAppExeName}"; Check: IsFullSelected

[Icons]
; Полный режим: единственный ярлык ведёт на merged exe (issue #9) — одно
; приложение под именем «Ekranchik».
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppAllInOneExeName}"; IconFilename: "{app}\{#MyAppIconName}"; Components: full
Name: "{userdesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppAllInOneExeName}"; IconFilename: "{app}\{#MyAppIconName}"; Tasks: desktopicon; Components: full
; Киоск-режим: ярлык на киоск exe, когда полный не выбран (Check — против
; дубля имени в выборочной установке с обоими компонентами).
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; IconFilename: "{app}\{#MyAppIconName}"; Components: kioskapp; Check: not IsFullSelected
Name: "{userdesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; IconFilename: "{app}\{#MyAppIconName}"; Tasks: desktopicon; Components: kioskapp; Check: not IsFullSelected

[Run]
Filename: "{app}\{#MyAppAllInOneExeName}"; Description: "{cm:LaunchProgram,{#StringChange(MyAppName, '&', '&&')}}"; Flags: nowait postinstall skipifsilent; Components: full
Filename: "{app}\{#MyAppExeName}"; Description: "{cm:LaunchProgram,{#StringChange(MyAppName, '&', '&&')}}"; Flags: nowait postinstall skipifsilent; Components: kioskapp; Check: not IsFullSelected

[Code]
const
  PrevAppUninstallKey = 'Software\Microsoft\Windows\CurrentVersion\Uninstall\{C6D2B1C1-827A-4D3F-B5FE-D372FEBF44C7}_is1';

var
  PrevVersion: String;
  PrevSetupType: String;
  PrevDetected: Boolean;

function IsFullSelected(): Boolean;
begin
  Result := WizardIsComponentSelected('full');
end;

{ DisplayVersion предыдущей установки с тем же AppId (HKCU — свой для
  PrivilegesRequired=lowest; HKLM — на случай старой машинной установки). }
function GetPrevDisplayVersion(): String;
var
  V: String;
begin
  Result := '';
  if RegQueryStringValue(HKCU, PrevAppUninstallKey, 'DisplayVersion', V) then
    Result := V
  else if RegQueryStringValue(HKLM, PrevAppUninstallKey, 'DisplayVersion', V) then
    Result := V;
end;

function GetPrevSetupType(): String;
var
  T: String;
begin
  Result := '';
  if RegQueryStringValue(HKCU, PrevAppUninstallKey, 'Inno Setup: Setup Type', T) then
    Result := T
  else if RegQueryStringValue(HKLM, PrevAppUninstallKey, 'Inno Setup: Setup Type', T) then
    Result := T;
end;

{ Признак предыдущей установки без записи в реестре: каталог по умолчанию
  уже несёт exe или настройки Ekranchik (портативный/дев-запуск, ключ
  Uninstall отсутствует или снесён). }
function HasPrevSettings(): Boolean;
var
  Dir: String;
begin
  Dir := ExpandConstant('{localappdata}\{#MyAppName}');
  Result :=
    FileExists(Dir + '\{#MyAppExeName}') or
    FileExists(Dir + '\kiosk_config.json') or
    FileExists(Dir + '\allinone_config.json');
end;

{ Очередной числовой кусок версии; P сдвигается за разделитель. }
function NumPart(const S: String; var P: Integer): Integer;
var
  N: Integer;
begin
  N := 0;
  while (P <= Length(S)) and (S[P] >= '0') and (S[P] <= '9') do
  begin
    N := N * 10 + (Ord(S[P]) - Ord('0'));
    P := P + 1;
  end;
  if (P <= Length(S)) and (S[P] = '.') then
    P := P + 1;
  while (P <= Length(S)) and ((S[P] < '0') or (S[P] > '9')) do
    P := P + 1;
  Result := N;
end;

{ -1: A < B; 0: равны; 1: A > B. "1.0.10" > "1.0.3". }
function CompareVersions(const A, B: String): Integer;
var
  PA, PB, NA, NB: Integer;
begin
  Result := 0;
  PA := 1;
  PB := 1;
  while (PA <= Length(A)) or (PB <= Length(B)) do
  begin
    NA := NumPart(A, PA);
    NB := NumPart(B, PB);
    if NA <> NB then
    begin
      if NA < NB then
        Result := -1
      else
        Result := 1;
      Exit;
    end;
  end;
end;

function InitializeSetup(): Boolean;
begin
  PrevVersion := GetPrevDisplayVersion();
  PrevSetupType := GetPrevSetupType();
  PrevDetected := (PrevVersion <> '') or HasPrevSettings();
  Result := True;
end;

{ Признаки предыдущей установки: запись в реестре по AppId или данные
  Ekranchik в каталоге по умолчанию. Пропускаем выбор папки — каталог
  наследуется UsePreviousAppDir, заодно умирает системный промпт про
  существующую папку. Чистая установка: страница на месте, без изменений. }
function ShouldSkipPage(PageID: Integer): Boolean;
begin
  Result := False;
  if (PageID = wpSelectDir) and PrevDetected then
    Result := True;
end;

{ Апгрейд: явное «Обновление Ekranchik» в заголовке и приветствии; версия
  X -> Y — когда известна из реестра, данные-без-версии — без номера.
  Чистая установка: тексты мастера не трогаем. }
procedure InitializeWizard();
begin
  if PrevVersion <> '' then
  begin
    WizardForm.Caption := 'Обновление Ekranchik ' + PrevVersion + ' -> {#MyAppVersion}';
    WizardForm.WelcomeLabel1.Caption := 'Вас приветствует обновление Ekranchik';
    WizardForm.WelcomeLabel2.Caption := 'Обнаружена установленная версия ' + PrevVersion + '.' + #13#10 +
      'Будет установлена версия {#MyAppVersion}. Данные и настройки сохраняются.';
  end
  else if PrevDetected then
  begin
    WizardForm.Caption := 'Обновление Ekranchik';
    WizardForm.WelcomeLabel1.Caption := 'Вас приветствует обновление Ekranchik';
    WizardForm.WelcomeLabel2.Caption := 'Обнаружены настройки и данные предыдущей установки.' + #13#10 +
      'Будет установлена версия {#MyAppVersion}. Данные и настройки сохраняются.';
  end;
end;

{ Блок «Обновление» на готовой странице: найденная версия -> новая;
  данные без записи в реестре — без номера версии.
  Стиль мастера не меняется — только текст сводки. }
function UpdateReadyMemo(Space, NewLine, MemoUserInfoInfo, MemoDirInfo, MemoTypeInfo,
  MemoComponentsInfo, MemoGroupInfo, MemoTasksInfo: String): String;
var
  S: String;
begin
  S := '';
  if MemoDirInfo <> '' then
    S := S + MemoDirInfo + NewLine + NewLine;
  if MemoTypeInfo <> '' then
    S := S + MemoTypeInfo + NewLine + NewLine;
  if MemoComponentsInfo <> '' then
    S := S + MemoComponentsInfo + NewLine + NewLine;
  if MemoGroupInfo <> '' then
    S := S + MemoGroupInfo + NewLine + NewLine;
  if MemoTasksInfo <> '' then
    S := S + MemoTasksInfo + NewLine + NewLine;
  if PrevDetected then
  begin
    S := S + 'Обновление' + NewLine + Space;
    if PrevVersion <> '' then
      S := S + 'Обнаружена версия ' + PrevVersion + ' -> будет установлена {#MyAppVersion}.'
    else
      S := S + 'Обнаружены настройки и данные предыдущей установки.';
    if PrevSetupType <> '' then
      S := S + NewLine + Space + 'Предыдущий тип установки: ' + PrevSetupType + '.';
    S := S + NewLine + Space +
      'Данные и настройки (%LOCALAPPDATA%\Ekranchik) сохраняются.';
  end
  else
    S := S + 'Установка' + NewLine + Space +
      'Будет установлена версия {#MyAppVersion} (предыдущих установок не найдено).';
  Result := S;
end;

{ Даунгрейд/та же версия — только осознанно: предупреждение с подтверждением.
  Апгрейд идёт без лишних вопросов. }
function NextButtonClick(CurPageID: Integer): Boolean;
var
  Cmp: Integer;
begin
  Result := True;
  if (CurPageID = wpReady) and (PrevVersion <> '') then
  begin
    Cmp := CompareVersions(PrevVersion, '{#MyAppVersion}');
    if Cmp = 0 then
    begin
      if MsgBox('Уже установлена версия ' + PrevVersion + '.' + #13#10 +
        'Продолжить переустановку версии {#MyAppVersion}?',
        mbConfirmation, MB_YESNO) <> IDYES then
        Result := False;
    end
    else if Cmp > 0 then
    begin
      if MsgBox('Обнаружена более новая версия ' + PrevVersion +
        ', чем устанавливаемая {#MyAppVersion}.' + #13#10 +
        'Продолжить даунгрейд? Данные и настройки сохраняются, ' +
        'но новая функциональность будет утрачена.',
        mbConfirmation, MB_YESNO) <> IDYES then
        Result := False;
    end;
  end;
end;
