; EkranchikSetup — один установщик, два приложения (issue #04).
;
;   «Только киоск»  — экран на отдельном компьютере: Ekranchik.exe +
;                     WebView2-загрузчик, runtime-файлы, конфиг, картинки
;                     и сам Microsoft Edge WebView2 Runtime (issue #11).
;   «Сервер»        — фоновое приложение: EkranchikServer.exe + встроенный
;                     Python, backend, собранный веб-интерфейс.
;   «Оба на одной машине» — выборочная установка с двумя галочками.

; WebView2 Runtime (issue #11). Своего бэкенда у экрана нет, но без
; вечнозелёного рантайма WebView2 окно не откроется, а на чистой
; корпоративной машине рантайма может не быть. Установщик ставит его сам:
; если по реестру рантайма нет (признаки per-machine и per-user из
; документации Microsoft), скачивается официальный вечнозелёный загрузчик
; (~2 МБ) и запускается с /silent /install — без вопросов и без перезагрузки.
; Прав администратора установщику не нужны (PrivilegesRequired=lowest),
; поэтому рантайм встаёт в профиль того же пользователя, что и сам экран.
; Нет сети — установка не падает: после установки оператор получает внятное
; сообщение (в тихой установке — текстом в
; %LOCALAPPDATA%\Ekranchik\logs\install-webview2.txt).

; Устаревший автозапуск (issue #11). Значение EkranchikAllInOne в
; HKCU\Software\Microsoft\Windows\CurrentVersion\Run удаляет установщик:
; на машине, где поставили только экран и сервер так и не запускали, чистить
; его некому, а Windows при каждом входе пытается запустить уже несуществующий
; файл. Сервер по-прежнему делает то же самое при старте — как страховка.
;
; Общего компонента с файлами WebView2 больше нет: они нужны только экрану.
; Два ярлыка в «Пуске»: «Ekranchik (киоск)» и «Ekranchik (сервер)», плюс те же
; два на рабочем столе по задаче desktopicon. Каждый ярлык ведёт на своё
; приложение и создаётся только при выбранном компоненте.
;
; Повторный запуск меняет состав: снятие галочки удаляет файлы и ярлыки своего
; приложения (в «Пуске» и на рабочем столе) секцией [InstallDelete]. Каталог
; данных и живые настройки (%LOCALAPPDATA%\Ekranchik: data/, *.json, logs/)
; установкой, обновлением и удалением компонентов НЕ затрагиваются — они
; нигде ниже не перечислены.
; Файлы и ярлыки прежней поставки EkranchikAllInOne вычищаются
; всегда: разделённых приложений он больше не запускает.
;
; Сборка пакета перед компиляцией (порядок важен):
;   1. Киоск:        рядом с этим файлом должен лежать Ekranchik.exe
;                    (+ WebView2Loader.dll, runtimes/, idle_clock.html,
;                     kiosk_config.json, ktm_colored.png, launcher.ico).
;   2. Сервер:       dotnet publish source_code\EkranchikServer\EkranchikServer.csproj -c Release -r win-x64 --self-contained -p:PublishSingleFile=true "-p:Version=$(Get-Content ..\VERSION)"
;                    (штамп из корневого VERSION; без флага версия подхватится
;                    сама через source_code\Directory.Build.props).
;                    Даёт launcher\EkranchikServer.exe. Рядом раскладывается
;                    пакет заводской машины (ниже шаг 3).
;   3. Python-пакет: powershell -ExecutionPolicy Bypass -File ..\scripts\build-full-package.ps1
;                    (раскладывает ..\dist-full\{python,backend,dist}).
;
; Компиляция: ISCC.exe launcher.iss (Inno Setup 6).
; Песочница без компилятора: структурная валидация — каждый Source секции
; [Files] существует на диске после шагов 1–3 (python/ и EkranchikServer.exe —
; артефакты полной сборки, в сухом прогоне отсутствуют штатно).

#define MyAppName "Ekranchik"
#define MyAppPublisher "Mavka"
#define MyAppExeName "Ekranchik.exe"
#define MyAppServerExeName "EkranchikServer.exe"
; Прежняя поставка: файлы и ярлыки вычищаются всегда.
#define MyAppLegacyExeName "EkranchikAllInOne.exe"
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
; Апгрейд-путь: каталог, тип установки (kiosk/server/custom) и задачи
; наследуются от предыдущей установки с тем же AppId — состав не сбрасывается
; молча.
UsePreviousAppDir=yes
UsePreviousSetupType=yes
UsePreviousTasks=yes

[Languages]
Name: "russian"; MessagesFile: "compiler:Languages\Russian.isl"

[Types]
Name: "kiosk"; Description: "Только киоск (экран на отдельном компьютере)"
Name: "server"; Description: "Сервер: фоновое приложение"
Name: "custom"; Description: "Оба на одной машине (выборочная установка)"; Flags: iscustom

[Components]
Name: "kiosk"; Description: "Экран киоска Ekranchik: приложение, загрузчик WebView2, конфиг, картинки (рантайм WebView2 ставит установщик)"; Types: kiosk custom
Name: "server"; Description: "Сервер Ekranchik: фоновое приложение, встроенный Python, бэкенд и веб-интерфейс"; Types: server custom

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[Files]
; --- Компонент «kiosk»: самостоятельный процесс экрана киоска. ---
; kiosk_config.json ставится только на чистую установку (onlyifdoesntexist):
; установщик одновременно кладёт seed по умолчанию и НЕ затирает живые
; настройки пользователя при обновлении/переустановке/смене состава.
; Seed кладёт scripts/build-full-installer.ps1 и он совпадает с тем, что
; приложение само пишет в пустой конфиг (адрес дашборда с портом 8083 из
; глоссария, монитор 0, оба признака выключены): установщик не должен
; менять поведение экрана. Оба признака выключены не просто так — с
; включённым «автозапуск на втором мониторе» окно настроек на двух мониторах
; не показывается вовсе, и оператор не попадёт в настройки.
Source: "{#MyAppExeName}"; DestDir: "{app}"; Flags: ignoreversion; Components: kiosk
Source: "WebView2Loader.dll"; DestDir: "{app}"; Flags: ignoreversion; Components: kiosk
Source: "runtimes\*"; DestDir: "{app}\runtimes"; Flags: ignoreversion recursesubdirs createallsubdirs; Components: kiosk
Source: "idle_clock.html"; DestDir: "{app}"; Flags: ignoreversion; Components: kiosk
Source: "kiosk_config.json"; DestDir: "{app}"; Flags: ignoreversion onlyifdoesntexist; Components: kiosk
Source: "ktm_colored.png"; DestDir: "{app}"; Flags: ignoreversion; Components: kiosk
; --- Иконка нужна обоим приложениям (ярлыки сервера ссылаются на неё) ---
; и удаляется, только когда не выбран ни один компонент.
Source: "{#MyAppIconName}"; DestDir: "{app}"; Flags: ignoreversion; Components: kiosk server
; --- Компонент «server»: фоновое приложение + раскладка рядом (контракт
; ADR 0002): сервер ищет backend/, dist/ и python/ рядом с собой. ---
Source: "{#MyAppServerExeName}"; DestDir: "{app}"; Flags: ignoreversion; Components: server
Source: "EkranchikServer.dll"; DestDir: "{app}"; Flags: ignoreversion skipifsourcedoesntexist; Components: server
Source: "EkranchikServer.deps.json"; DestDir: "{app}"; Flags: ignoreversion skipifsourcedoesntexist; Components: server
Source: "EkranchikServer.runtimeconfig.json"; DestDir: "{app}"; Flags: ignoreversion skipifsourcedoesntexist; Components: server
Source: "..\dist-full\backend\*"; DestDir: "{app}\backend"; Flags: ignoreversion recursesubdirs createallsubdirs; Components: server
Source: "..\dist-full\dist\*"; DestDir: "{app}\dist"; Flags: ignoreversion recursesubdirs createallsubdirs; Components: server
Source: "..\dist-full\python\*"; DestDir: "{app}\python"; Flags: ignoreversion recursesubdirs createallsubdirs; Components: server

[InstallDelete]
; Снятие галочки на повторной установке удаляет ТОЛЬКО своё приложение.
; data/, *.json, logs/ здесь намеренно отсутствуют: данные и живые настройки
; переживают и установку, и удаление любого компонента. На чистой установке
; удалять нечего — секция молча ничего не делает.
; Снятие галочки удаляет и ярлыки приложения (issue #12): без этого в «Пуске»
; оставалась ссылка на exe, которого на машине больше нет. Рабочий стол
; удаляется тем же правилом — ярлыка там могло не быть вовсе, Type: files
; на отсутствующем файле молчит.
Type: files; Name: "{app}\{#MyAppExeName}"; Check: not WizardIsComponentSelected('kiosk')
Type: files; Name: "{app}\WebView2Loader.dll"; Check: not WizardIsComponentSelected('kiosk')
Type: filesandordirs; Name: "{app}\runtimes"; Check: not WizardIsComponentSelected('kiosk')
Type: files; Name: "{app}\idle_clock.html"; Check: not WizardIsComponentSelected('kiosk')
Type: files; Name: "{app}\ktm_colored.png"; Check: not WizardIsComponentSelected('kiosk')
Type: files; Name: "{group}\{#MyAppName} (киоск).lnk"; Check: not WizardIsComponentSelected('kiosk')
Type: files; Name: "{userdesktop}\{#MyAppName} (киоск).lnk"; Check: not WizardIsComponentSelected('kiosk')
Type: files; Name: "{app}\{#MyAppIconName}"; Check: not (WizardIsComponentSelected('kiosk') or WizardIsComponentSelected('server'))
Type: files; Name: "{app}\{#MyAppServerExeName}"; Check: not WizardIsComponentSelected('server')
Type: files; Name: "{app}\EkranchikServer.dll"; Check: not WizardIsComponentSelected('server')
Type: files; Name: "{app}\EkranchikServer.deps.json"; Check: not WizardIsComponentSelected('server')
Type: files; Name: "{app}\EkranchikServer.runtimeconfig.json"; Check: not WizardIsComponentSelected('server')
Type: filesandordirs; Name: "{app}\backend"; Check: not WizardIsComponentSelected('server')
Type: filesandordirs; Name: "{app}\dist"; Check: not WizardIsComponentSelected('server')
Type: filesandordirs; Name: "{app}\python"; Check: not WizardIsComponentSelected('server')
Type: files; Name: "{group}\{#MyAppName} (сервер).lnk"; Check: not WizardIsComponentSelected('server')
Type: files; Name: "{userdesktop}\{#MyAppName} (сервер).lnk"; Check: not WizardIsComponentSelected('server')
; --- Вычистка прежней поставки (общий AppId): на любой машине с
; прежней поставкой мог остаться EkranchikAllInOne.exe и его ярлыки. ---
Type: files; Name: "{app}\{#MyAppLegacyExeName}"
Type: files; Name: "{app}\EkranchikAllInOne.dll"
Type: files; Name: "{app}\EkranchikAllInOne.deps.json"
Type: files; Name: "{app}\EkranchikAllInOne.runtimeconfig.json"
Type: files; Name: "{group}\{#MyAppName}.lnk"
Type: files; Name: "{userdesktop}\{#MyAppName}.lnk"
Type: files; Name: "{group}\{#MyAppName} Полный пакет.lnk"
Type: files; Name: "{userdesktop}\{#MyAppName} Полный пакет.lnk"
; Конфиг прежней поставки (PythonExe/KioskExe/UseExternalKiosk): ADR 0004 не
; читает его вовсе, но на машине с прежней установкой он остаётся лежать в
; каталоге приложения рядом с живым server_config.json.
Type: files; Name: "{app}\allinone_config.json"

[UninstallDelete]
; Один каталог, который unins000 сам дочиста не уберёт: backend\. В пакете
; (scripts/build-full-package.ps1) кэши байткода вычищены, а работа сервера их
; создаёт заново — backend\app\__pycache__, alembic\__pycache__ и т.д. Файлы
; установщику незнакомы, значит после удаления остаётся непустой backend\ от
; уже удалённого сервера. dist\ и python\ здесь не перечислены: в python\
; кэши приходят из pip install (то есть знакомы установщику) и уходят вместе
; с ним, а в dist\ приложение вообще не пишет.
; data\, *.json и logs\ по-прежнему не трогаются — это данные и настройки.
Type: filesandordirs; Name: "{app}\backend"

[Icons]
; Два ярлыка в «Пуске» и те же два на рабочем столе по задаче desktopicon.
; Каждый появляется только при выбранном компоненте.
Name: "{group}\{#MyAppName} (киоск)"; Filename: "{app}\{#MyAppExeName}"; IconFilename: "{app}\{#MyAppIconName}"; Components: kiosk
Name: "{group}\{#MyAppName} (сервер)"; Filename: "{app}\{#MyAppServerExeName}"; IconFilename: "{app}\{#MyAppIconName}"; Components: server
Name: "{userdesktop}\{#MyAppName} (киоск)"; Filename: "{app}\{#MyAppExeName}"; IconFilename: "{app}\{#MyAppIconName}"; Tasks: desktopicon; Components: kiosk
Name: "{userdesktop}\{#MyAppName} (сервер)"; Filename: "{app}\{#MyAppServerExeName}"; IconFilename: "{app}\{#MyAppIconName}"; Tasks: desktopicon; Components: server

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "{cm:LaunchProgram,{#StringChange(MyAppName, '&', '&&')}} (киоск)"; Flags: nowait postinstall skipifsilent; Components: kiosk
Filename: "{app}\{#MyAppServerExeName}"; Description: "{cm:LaunchProgram,{#StringChange(MyAppName, '&', '&&')}} (сервер)"; Flags: nowait postinstall skipifsilent; Components: server

[Code]
const
  PrevAppUninstallKey = 'Software\Microsoft\Windows\CurrentVersion\Uninstall\{C6D2B1C1-827A-4D3F-B5FE-D372FEBF44C7}_is1';
  { Автозапуск прежнего единого приложения (ADR 0004): на машине, где стоял
    только экран, сервер не запускали и убрать значение было некому. }
  WinRunKey = 'Software\Microsoft\Windows\CurrentVersion\Run';
  LegacyAutostartValue = 'EkranchikAllInOne';
  { Вечнозелёный WebView2 Runtime: официальный загрузчик Microsoft (~2 МБ) и
    реестровые признаки per-machine / per-user из документации Microsoft. }
  WebView2ClientKey = 'Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}';
  WebView2SetupUrl = 'https://go.microsoft.com/fwlink/p/?LinkId=2124703';
  WebView2SetupFile = 'MicrosoftEdgeWebview2Setup.exe';

var
  PrevVersion: String;
  PrevSetupType: String;
  PrevDetected: Boolean;
  WebView2SetupPath: String;  { '' — ставить нечего }
  WebView2Error: String;      { '' — замечаний к рантайму нет }
  WebView2Detail: String;     { техническая причина — в лог установки }

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

{ Имя типа из реестра -> человекочитаемое. Надписи обязаны совпадать с
  описаниями из [Types]: мастер показывает при выборе и в сводке одно и то
  же («Оба на одной машине», а не внутреннее «Выборочная установка»).
  Прежний тип «full» тоже разворачивается в текст: в сводке пользователь
  должен видеть, что стояло раньше, а не внутреннее имя. }
function SetupTypeLabel(const T: String): String;
begin
  Result := T;
  if CompareText(T, 'kiosk') = 0 then
    Result := 'Только киоск (экран на отдельном компьютере)'
  else if CompareText(T, 'server') = 0 then
    Result := 'Сервер: фоновое приложение'
  else if CompareText(T, 'custom') = 0 then
    Result := 'Оба на одной машине (выборочная установка)'
  else if CompareText(T, 'full') = 0 then
    Result := 'Единое приложение EkranchikAllInOne (прежняя поставка)';
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
    FileExists(Dir + '\{#MyAppServerExeName}') or
    FileExists(Dir + '\{#MyAppLegacyExeName}') or
    FileExists(Dir + '\kiosk_config.json') or
    FileExists(Dir + '\server_config.json') or
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
      S := S + NewLine + Space + 'Предыдущий тип установки: ' + SetupTypeLabel(PrevSetupType) + '.';
    S := S + NewLine + Space +
      'Данные и настройки (%LOCALAPPDATA%\Ekranchik) сохраняются.';
  end
  else
    S := S + 'Установка' + NewLine + Space +
      'Будет установлена версия {#MyAppVersion} (предыдущих установок не найдено).';
  Result := S;
end;

{ Даунгрейд/та же версия — только осознанно: предупреждение с подтверждением.
  Апгрейд идёт без лишних вопросов. В тихой установке (/SILENT, /VERYSILENT)
  вопросов быть не может: повторная установка на заводской машине идёт
  без пользователя и не должна висеть на MsgBox. }
function NextButtonClick(CurPageID: Integer): Boolean;
var
  Cmp: Integer;
begin
  Result := True;
  if (CurPageID = wpReady) and (PrevVersion <> '') and not WizardSilent then
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

{ --- WebView2 Runtime и устаревший автозапуск (issue #11) ----------------

  Рантайм WebView2 уже есть на машине. Признаки — реестровые ключи
  per-machine (HKLM, ветка WOW6432Node) и per-user (HKCU) из документации
  Microsoft; значение 0.0.0.0 рантаймом не считается. }
function WebView2RuntimeInstalled(): Boolean;
var
  V: String;
  Machine, User: Boolean;
begin
  V := '';
  Machine := RegQueryStringValue(HKLM,
    'SOFTWARE\WOW6432Node\' + WebView2ClientKey, 'pv', V) and (V <> '') and (V <> '0.0.0.0');
  V := '';
  User := RegQueryStringValue(HKCU,
    'Software\' + WebView2ClientKey, 'pv', V) and (V <> '') and (V <> '0.0.0.0');
  Result := Machine or User;
end;

{ Скачанное — настоящий exe установщика, а не страница с ошибкой: ссылка
  Microsoft на неизвестный LinkId отдаёт 200 OK с html. }
function DownloadedFileIsExe(const Path: String): Boolean;
var
  F: TFileStream;
  Head: AnsiString;
begin
  Result := False;
  if not FileExists(Path) then
    Exit;
  F := TFileStream.Create(Path, 0);
  try
    SetLength(Head, 2);
    F.Read(Head, 2);
  finally
    F.Free;
  end;
  Result := Head = 'MZ';
end;

{ Рантайм нужен только экрану и ставится только когда его нет. Скачиваем
  официальный вечнозелёный загрузчик во временный каталог установщика (сети
  нет — DownloadTemporaryFile бросает исключение, установка не падает: причина
  уходит оператору после установки, см. ReportWebView2Missing). }
procedure PrepareWebView2Runtime();
var
  Dest: String;
begin
  WebView2SetupPath := '';
  if not WizardIsComponentSelected('kiosk') then
    Exit;
  if WebView2RuntimeInstalled then
  begin
    Log('WebView2 Runtime уже установлен — установщик его не трогает.');
    Exit;
  end;
  Dest := ExpandConstant('{tmp}\' + WebView2SetupFile);
  try
    DownloadTemporaryFile(WebView2SetupUrl, WebView2SetupFile, '', nil);
    if not DownloadedFileIsExe(Dest) then
    begin
      DeleteFile(Dest);
      RaiseException('по ссылке отвечает не загрузчик, а страница');
    end;
    WebView2SetupPath := Dest;
    Log('Загрузчик WebView2 Runtime скачан: ' + Dest);
  except
    WebView2Detail := GetExceptionMessage;
    WebView2Error :=
      'Не удалось получить установщик Microsoft Edge WebView2 Runtime (' +
      WebView2SetupUrl + ').';
    Log(WebView2Error + ' ' + WebView2Detail);
  end;
end;

{ /silent /install — без вопросов и без требования перезагрузки. Прав
  администратора установщику не нужны (PrivilegesRequired=lowest), поэтому
  рантайм встаёт в профиль того же пользователя, что и сам экран; уже
  установленный (в т.ч. общесистемный) мы не трогаем. }
procedure InstallWebView2Runtime();
var
  Res: Integer;
begin
  if WebView2SetupPath = '' then
    Exit;
  if not Exec(WebView2SetupPath, '/silent /install', '', SW_HIDE,
    ewWaitUntilTerminated, Res) then
  begin
    WebView2Detail := 'код запуска ' + IntToStr(Res);
    WebView2Error := 'Не удалось запустить установщик Microsoft Edge WebView2 Runtime.';
    Log(WebView2Error + ' ' + WebView2Detail);
    Exit;
  end;
  if (Res <> 0) or not WebView2RuntimeInstalled then
  begin
    WebView2Detail := 'код ' + IntToStr(Res);
    WebView2Error := 'Microsoft Edge WebView2 Runtime не установился.';
    Log(WebView2Error + ' ' + WebView2Detail);
  end
  else
    Log('WebView2 Runtime установлен.');
end;

{ Рантайм не встал — установку откатывать нечем и незачем, но оператор
  обязан узнать об этом сразу: иначе экран молча не откроется. На явной
  установке — сообщение; в тихой (/SILENT: вопросов быть не может) — текст
  в лог приложений, иначе на заводской машине никто не узнает, почему
  дашборд не показывается. }
procedure ReportWebView2Missing();
var
  NoteFile, Note: String;
begin
  if WebView2Error = '' then
    Exit;
  Note := GetDateTimeString('yyyy-mm-dd hh:nn:ss', '-', ':') + ' EkranchikSetup: ' +
    WebView2Error + #13#10 +
    'Без Microsoft Edge WebView2 Runtime экран киоска не откроется. ' +
    'Скачать рантайм: https://developer.microsoft.com/microsoft-edge/webview2/' + #13#10;
  if WebView2Detail <> '' then
    Note := Note + 'Подробности: ' + WebView2Detail + #13#10;
  NoteFile := ExpandConstant('{app}\logs\install-webview2.txt');
  ForceDirectories(ExtractFileDir(NoteFile));
  SaveStringToFile(NoteFile, Note, True);
  if not WizardSilent then
    MsgBox(WebView2Error + #13#10#13#10 +
      'Экран киоска до установки Microsoft Edge WebView2 Runtime не откроется.' + #13#10 +
      'Скачайте рантайм ' +
      '(https://developer.microsoft.com/microsoft-edge/webview2/) и запустите ' +
      'установку ещё раз — установщик поставит его сам.',
      mbError, MB_OK);
end;

{ Устаревший автозапуск прежнего единого приложения: на машине, где поставили
  только экран, сервер не запускают, а значение осталось бы навсегда, и
  Windows при каждом входе пыталась бы запустить несуществующий файл. Чистит
  установщик; сервер по-прежнему делает то же самое при старте (страховка). }
procedure RemoveLegacyAutostart();
begin
  if RegDeleteValue(HKCU, WinRunKey, LegacyAutostartValue) then
    Log('Удалено устаревшее значение автозапуска ' + LegacyAutostartValue + '.');
end;

{ Загрузчик рантайма готовим между выбором компонентов и раскладкой файлов,
  сам рантайм ставим после файлов и до [Run]: приложения из [Run] стартуют
  уже с рабочим WebView2. }
procedure CurStepChanged(CurStep: TSetupStep);
begin
  if CurStep = ssInstall then
    PrepareWebView2Runtime()
  else if CurStep = ssPostInstall then
  begin
    RemoveLegacyAutostart;
    InstallWebView2Runtime;
    ReportWebView2Missing;
  end;
end;
