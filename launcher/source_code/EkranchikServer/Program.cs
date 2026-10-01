// EkranchikServer — фоновое приложение сервера (ADR 0004; экран киоска и
// сервер разнесены в два приложения).
//
// Сценарий: двойной клик → окно настроек (Excel, OPC UA, симуляция, доступ
// по локалке, автозапуск) → запуск backend (python -m uvicorn) → poll
// /health → трей с «Настройки» / «Выход». Своего окна у приложения нет:
// дашборд открывает отдельный экран киоска (Ekranchik.exe), оператор вводит
// ему «Адрес для экранов» из окна настроек сервера.
// Флаг --silent (и запись автозапуска HKCU ...\Run с ним): старт в трей без
// окна, стек поднимается сам.
//
// Конфигурирование: JSON %LOCALAPPDATA%\Ekranchik\server_config.json
// + перекрывающие env-переменные EKRANCHIK_* (см. ServerConfig).
// В трее НЕТ портов/статусов — только действия.
//
// Тестовые крючки для smoke (не показываются пользователю):
//   --auto-exit-after-ready=N — после готовности сервера ждёт N сек и идёт по
//     ТОМУ ЖЕ коду Shutdown(), что и пункт трея «Выход»; подразумевает тихий
//     режим (без окна настроек);
//   --crash-after-ready=N — после готовности сервера ждёт N сек и убивает себя
//     через TerminateProcess (без managed-очистки): проверяет, что Job Object
//     добивает дочерние процессы; тоже тихий режим;
//   --dump-config — печатает итоговый конфиг (файл + env) в stdout и выходит;
//   --autostart=on|off [--run-key=<subkey>] — включает/выключает автозапуск
//     (по умолчанию в настоящем Run; с --run-key — в тестовом подключении
//     HKCU\<subkey> под тем же именем значения) и выходит;
//   --run-key=<subkey> — действует и на обычном старте: и запись автозапуска
//     сервера, и чистка устаревшего значения идут в тестовое
//     подключение, настоящий Run машины не пачкается.

using System;
using System.Diagnostics;
using System.Drawing;
using System.IO;
using System.Linq;
using System.Net.Http;
using System.Text.Json;
using System.Threading;
using System.Threading.Tasks;
using System.Windows.Forms;
using EkranchikShared;
using Microsoft.Win32;

namespace EkranchikServer
{
    static class Program
    {
        [STAThread]
        static int Main(string[] args)
        {
            Application.SetHighDpiMode(HighDpiMode.PerMonitorV2);
            Application.EnableVisualStyles();
            Application.SetCompatibleTextRenderingDefault(false);
            // Падение UI-потока больше не роняет весь стек (issue #9):
            // лог + корректная остановка сервера и трея. Режим ставится ДО
            // создания скрытых контролов синхронизации.
            Application.SetUnhandledExceptionMode(UnhandledExceptionMode.CatchException);
            Application.ThreadException += (s, e) => ServerContext.ReportUiCrash(e.Exception);
            AppDomain.CurrentDomain.UnhandledException += (s, e) => ServerContext.ReportCrash(e.ExceptionObject);
            // Контекст синхронизации UI-потока: окно настроек создаётся только
            // на Main-потоке (issue #9).
            SynchronizationContext.SetSynchronizationContext(new WindowsFormsSynchronizationContext());

            int autoExitAfterReady = 0;
            int crashAfterReady = 0;
            bool silent = false;
            bool dumpConfig = false;
            bool selfTest = false;
            string? autostartArg = null;
            string? runKeyArg = null;
            foreach (var arg in args)
            {
                const string autoPrefix = "--auto-exit-after-ready=";
                const string crashPrefix = "--crash-after-ready=";
                const string autostartPrefix = "--autostart=";
                const string runKeyPrefix = "--run-key=";
                if (arg.StartsWith(autoPrefix, StringComparison.OrdinalIgnoreCase)
                    && int.TryParse(arg.Substring(autoPrefix.Length), out int seconds)
                    && seconds > 0)
                {
                    autoExitAfterReady = seconds;
                }
                else if (arg.StartsWith(crashPrefix, StringComparison.OrdinalIgnoreCase)
                    && int.TryParse(arg.Substring(crashPrefix.Length), out int crashSeconds)
                    && crashSeconds > 0)
                {
                    crashAfterReady = crashSeconds;
                }
                else if (arg.Equals("--silent", StringComparison.OrdinalIgnoreCase))
                {
                    silent = true;
                }
                else if (arg.Equals("--dump-config", StringComparison.OrdinalIgnoreCase))
                {
                    dumpConfig = true;
                }
                else if (arg.Equals("--self-test", StringComparison.OrdinalIgnoreCase))
                {
                    selfTest = true;
                }
                else if (arg.StartsWith(autostartPrefix, StringComparison.OrdinalIgnoreCase))
                {
                    autostartArg = arg.Substring(autostartPrefix.Length);
                }
                else if (arg.StartsWith(runKeyPrefix, StringComparison.OrdinalIgnoreCase))
                {
                    runKeyArg = arg.Substring(runKeyPrefix.Length);
                }
            }

            // Крючок smoke: round-trip автозапуска в тестовом ключе реестра.
            if (autostartArg != null)
            {
                bool enable = autostartArg.Equals("on", StringComparison.OrdinalIgnoreCase)
                    || autostartArg.Equals("1", StringComparison.OrdinalIgnoreCase)
                    || autostartArg.Equals("true", StringComparison.OrdinalIgnoreCase);
                try
                {
                    WindowsAutoStart.Apply(enable, WindowsAutoStart.ServerValueName, WindowsAutoStart.ServerArgsSuffix, runKeyArg);
                    Console.WriteLine($"autostart {(enable ? "enabled" : "disabled")} key={WindowsAutoStart.EffectiveKeyPath(runKeyArg)}");
                    return 0;
                }
                catch (Exception ex)
                {
                    Console.Error.WriteLine($"autostart failed: {ex.Message}");
                    return 1;
                }
            }

            // Постоянные кейсы shared-модуля: лог в tmp + exit code, без UI.
            if (selfTest)
            {
                int failures = EkranchikShared.UpdateSelfTest.Run(out string selfTestLog);
                try
                {
                    Console.WriteLine($"self-test: {(failures == 0 ? "ALL OK" : failures + " FAILURES")} log={selfTestLog}");
                }
                catch { }
                return failures == 0 ? 0 : 1;
            }

            var config = ServerConfig.Load();

            // Крючок smoke: проверка persist пяти настроек (файл + env).
            if (dumpConfig)
            {
                Console.WriteLine(JsonSerializer.Serialize(config,
                    new JsonSerializerOptions { WriteIndented = false }));
                return 0;
            }

            // Один экземпляр на машину: второй занимал бы тот же порт и
            // падал бы с "backend exited early", оставляя пользователя с
            // ошибкой вместо работающего приложения. Мьютекс держится до
            // конца процесса, умирает вместе с ним.
            using (var single = new Mutex(true, @"Local\EkranchikServer", out bool first))
            {
                if (!first)
                {
                    if (!silent)
                    {
                        try
                        {
                            MessageBox.Show(
                                "Сервер Ekranchik уже запущен — значок в трее, настройки открываются кликом по нему.\n" +
                                "Второй экземпляр не нужен: он занимает тот же порт.",
                                "Ekranchik (сервер)", MessageBoxButtons.OK, MessageBoxIcon.Information);
                        }
                        catch { }
                    }
                    return 0;
                }

                // smoke-хук идёт тем же тихим путём, что и --silent: без окна.
                // runKeyArg пробрасывается в контекст, чтобы проверка
                // автозапуска и чистки устаревшего значения шла в тестовом
                // подключении и не трогала настоящий Run машины.
                using (var context = new ServerContext(
                    config, autoExitAfterReady, crashAfterReady,
                    silent || autoExitAfterReady > 0 || crashAfterReady > 0,
                    runKeyArg))
                {
                    Application.Run(context);
                    return context.ExitCode;
                }
            }
        }
    }

    // === Конфигурация (JSON + env-переопределения). Настройки окна сервера
    // (путь Excel, адрес OPC UA, симуляция, доступ по локалке, автозапуск)
    // persist-ятся в server_config.json между запусками. ===
    sealed class ServerConfig
    {
        public string PythonExe { get; set; } = "";
        // Полная строка аргументов backend; {host} и {port} подставляются
        // автоматически из LanAccess/Port (аргументы у пользователя не хранятся).
        public string BackendArgs { get; set; } = "-m uvicorn app.main:app";
        public string BackendDir { get; set; } = "";
        public int Port { get; set; } = 8083;
        // Адрес, по которому сервер себя проверяет (здоровье и версии).
        // Обычно пусто — тогда localhost:Port. Перекрывается только env.
        public string DashboardUrl { get; set; } = "";
        // Дашборд виден с других машин локалки (--host 0.0.0.0). Выключено —
        // только этот компьютер (127.0.0.1).
        public bool LanAccess { get; set; } = true;
        // Крючок smoke: процесс-заглушка, который надо запустить после
        // готовности сервера (экрана киоска у сервера нет). Только env.
        public string AfterReadyExe { get; set; } = "";
        public string AfterReadyArgs { get; set; } = "";
        public int ReadyTimeoutSeconds { get; set; } = 90;

        // --- Issue #4: настройки окна (persist между запусками) ---
        // Сетевой путь к Excel-книге учёта.
        public string ExcelPath { get; set; } = "//ktm-disk/Оператор/Учет КПЗ 2026.xlsm";
        // Адрес реального OPC UA сервера.
        public string OpcuaEndpoint { get; set; } = "opc.tcp://172.17.11.115:4840/";
        // Тестовые данные (SIMULATION_ENABLED у backend).
        public bool SimulationEnabled { get; set; } = false;
        // Желаемый автозапуск Windows (реестр HKCU ...\Run синхронизируется
        // при старте и при сохранении окна настроек).
        public bool AutoStart { get; set; } = false;
        private static readonly string ConfigDir = Path.Combine(
            Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData), "Ekranchik");
        private static readonly string ConfigFile = Path.Combine(ConfigDir, "server_config.json");

        public string ResolvedBackendArgs =>
            $"{BackendArgs} --host {ResolvedHost} --port {Port}";
        public string ResolvedHost => LanAccess ? "0.0.0.0" : "127.0.0.1";

        public string ResolvedDashboardUrl =>
            string.IsNullOrWhiteSpace(DashboardUrl) ? $"http://localhost:{Port}" : DashboardUrl;
        // Адрес, который оператор вводит в настройках экрана киоска. Сборку
        // строки (подбор IP этой машины) делает общий код: сервер своего
        // обхода сетевых интерфейсов не держит.
        public string KioskAddress => EkranchikShared.KioskAddress.ForPort(Port);

        public static ServerConfig Load()
        {
            var config = new ServerConfig();
            if (File.Exists(ConfigFile))
            {
                try
                {
                    var loaded = JsonSerializer.Deserialize<ServerConfig>(File.ReadAllText(ConfigFile));
                    if (loaded != null) config = loaded;
                }
                catch { /* битый конфиг = дефолты, молча */ }
            }
            config.ApplyEnvironmentOverrides();
            config.ApplyDefaults();
            return config;
        }

        public void Save()
        {
            Directory.CreateDirectory(ConfigDir);
            string tmp = ConfigFile + ".tmp";
            File.WriteAllText(tmp, JsonSerializer.Serialize(this,
                new JsonSerializerOptions { WriteIndented = true }));
            File.Move(tmp, ConfigFile, overwrite: true);
        }

        private void ApplyEnvironmentOverrides()
        {
            string? Env(string name) => Environment.GetEnvironmentVariable(name);

            if (!string.IsNullOrWhiteSpace(Env("EKRANCHIK_PYTHON"))) PythonExe = Env("EKRANCHIK_PYTHON")!;
            if (!string.IsNullOrWhiteSpace(Env("EKRANCHIK_BACKEND_ARGS"))) BackendArgs = Env("EKRANCHIK_BACKEND_ARGS")!;
            if (!string.IsNullOrWhiteSpace(Env("EKRANCHIK_BACKEND_DIR"))) BackendDir = Env("EKRANCHIK_BACKEND_DIR")!;
            if (!string.IsNullOrWhiteSpace(Env("EKRANCHIK_AFTER_READY_EXE"))) AfterReadyExe = Env("EKRANCHIK_AFTER_READY_EXE")!;
            if (!string.IsNullOrWhiteSpace(Env("EKRANCHIK_AFTER_READY_ARGS"))) AfterReadyArgs = Env("EKRANCHIK_AFTER_READY_ARGS")!;
            if (!string.IsNullOrWhiteSpace(Env("EKRANCHIK_URL"))) DashboardUrl = Env("EKRANCHIK_URL")!;
            if (!string.IsNullOrWhiteSpace(Env("EKRANCHIK_EXCEL_PATH"))) ExcelPath = Env("EKRANCHIK_EXCEL_PATH")!;
            if (!string.IsNullOrWhiteSpace(Env("EKRANCHIK_OPCUA_ENDPOINT"))) OpcuaEndpoint = Env("EKRANCHIK_OPCUA_ENDPOINT")!;
            if (TryParseBool(Env("EKRANCHIK_SIMULATION"), out bool sim)) SimulationEnabled = sim;
            if (TryParseBool(Env("EKRANCHIK_AUTOSTART"), out bool autostart)) AutoStart = autostart;
            if (int.TryParse(Env("EKRANCHIK_PORT"), out int port) && port > 0 && port < 65536) Port = port;
            if (TryParseBool(Env("EKRANCHIK_LAN_ACCESS"), out bool lan)) LanAccess = lan;
            if (int.TryParse(Env("EKRANCHIK_READY_TIMEOUT_S"), out int timeout) && timeout > 0) ReadyTimeoutSeconds = timeout;
        }

        private static bool TryParseBool(string? value, out bool result)
        {
            if (value != null)
            {
                string v = value.Trim().ToLowerInvariant();
                if (v == "1" || v == "true" || v == "yes" || v == "on") { result = true; return true; }
                if (v == "0" || v == "false" || v == "no" || v == "off") { result = false; return true; }
            }
            result = false;
            return false;
        }

        // Env для дочернего процесса backend. Backend читает ГОЛЫЕ имена
        // (pydantic Settings без префикса, голое в приоритете) — их ставим
        // всегда; EKRANCHIK_*-алиасы — форвард-контракт с #5 (Packager).
        public void ApplyToBackendEnvironment(System.Collections.Generic.IDictionary<string, string?> env)
        {
            string sim = SimulationEnabled ? "true" : "false";
            env["SIMULATION_ENABLED"] = sim;
            env["OPCUA_ENDPOINT"] = OpcuaEndpoint;
            env["EXCEL_REAL_FILE_PATH"] = ExcelPath;
            env["EKRANCHIK_SIMULATION"] = sim;
            env["EKRANCHIK_OPCUA_ENDPOINT"] = OpcuaEndpoint;
            env["EKRANCHIK_EXCEL_PATH"] = ExcelPath;
        }

        private void ApplyDefaults()
        {
            string exeDir = AppContext.BaseDirectory;
            // Пустой PythonExe в config.json = искать интерпретатор пакета
            // (ResolvePythonExe): рядом с exe в установке, в dist-full/ — в
            // репозитории. Только если нет ни того, ни другого — системный
            // python: в репозитории он почти наверняка без зависимостей
            // бэкенда, и uvicorn падает с кодом 1.
            if (string.IsNullOrWhiteSpace(PythonExe))
                PythonExe = ResolvePythonExe(exeDir);
            if (string.IsNullOrWhiteSpace(BackendDir))
                BackendDir = ResolveBackendDir(exeDir);
        }

        // Прод-раскладка: backend/ рядом с exe. Дев-раскладка: подняться вверх
        // до корня репозитория, где лежит backend/app/main.py.
        private static string ResolveBackendDir(string exeDir)
        {
            string besideExe = Path.Combine(exeDir, "backend");
            if (File.Exists(Path.Combine(besideExe, "app", "main.py"))) return besideExe;

            var dir = new DirectoryInfo(exeDir);
            for (int i = 0; i < 8 && dir != null; i++)
            {
                string candidate = Path.Combine(dir.FullName, "backend");
                if (File.Exists(Path.Combine(candidate, "app", "main.py"))) return candidate;
                dir = dir.Parent;
            }
            return besideExe;
        }

        // Прод-раскладка: python\python.exe рядом с exe (его кладёт установщик).
        // Дев-раскладка: подняться вверх до корня репозитория и взять embedded
        // python из dist-full\ (собирается scripts/build-full-package.ps1) —
        // тогда exe из build/source_code/launcher запускает настоящий стек.
        private static string ResolvePythonExe(string exeDir)
        {
            string beside = Path.Combine(exeDir, "python", "python.exe");
            if (File.Exists(beside)) return beside;
            var dir = new DirectoryInfo(exeDir);
            for (int i = 0; i < 8 && dir != null; i++)
            {
                string candidate = Path.Combine(dir.FullName, "dist-full", "python", "python.exe");
                if (File.Exists(candidate)) return candidate;
                dir = dir.Parent;
            }
            return "python";
        }
    }

    // === Логгер с ротацией: один файл в день, хранить последние 7 суток ===
    sealed class RotatingLogger : IDisposable
    {
        private readonly string _logDir;
        private readonly string _prefix;
        private StreamWriter? _writer;
        private readonly object _lock = new();
        private bool _disposed;

        public string LogDir => _logDir;

        public RotatingLogger(string prefix)
        {
            _prefix = prefix;
            _logDir = Path.Combine(
                Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData),
                "Ekranchik", "logs");
            Directory.CreateDirectory(_logDir);
            PruneOldLogs();
            string file = Path.Combine(_logDir, $"{_prefix}-{DateTime.Now:yyyyMMdd}.log");
            _writer = new StreamWriter(new FileStream(file, FileMode.Append, FileAccess.Write, FileShare.ReadWrite))
            {
                AutoFlush = true
            };
            Write($"=== {prefix} started {DateTime.Now:yyyy-MM-dd HH:mm:ss} ===");
        }

        public void Write(string message)
        {
            lock (_lock)
            {
                if (_disposed || _writer == null) return;
                _writer.WriteLine($"[{DateTime.Now:HH:mm:ss.fff}] {message}");
            }
        }

        private void PruneOldLogs()
        {
            try
            {
                var cutoff = DateTime.Now.AddDays(-7);
                foreach (var file in Directory.GetFiles(_logDir, $"{_prefix}-*.log"))
                {
                    try
                    {
                        if (File.GetCreationTime(file) < cutoff) File.Delete(file);
                    }
                    catch { /* один плохой файл не роняет старт */ }
                }
                // Страховка от потопа: больше 10 файлов — удалить самые старые.
                var rest = Directory.GetFiles(_logDir, $"{_prefix}-*.log")
                    .OrderBy(File.GetCreationTime).ToArray();
                for (int i = 0; i + 10 < rest.Length; i++)
                {
                    try { File.Delete(rest[i]); } catch { }
                }
            }
            catch { }
        }

        public void Dispose()
        {
            lock (_lock)
            {
                if (_disposed) return;
                _disposed = true;
                try { _writer?.Dispose(); } catch { }
                _writer = null;
            }
        }
    }

    // === Модель настроек сервера для единого окна: обёртка ServerConfig.
    // URL и монитор скрыты — это настройки экрана киоска; сервер показывает
    // серверную секцию и «Адрес для экранов». ===
    sealed class ServerSettingsModel : ISettingsModel
    {
        private readonly ServerConfig _config;

        public ServerSettingsModel(ServerConfig config)
        {
            _config = config;
        }

        public string? Url => null;
        public string? ExcelPath => _config.ExcelPath;
        public string? OpcuaEndpoint => _config.OpcuaEndpoint;
        public bool Simulation => _config.SimulationEnabled;
        public bool? LanAccess => _config.LanAccess;
        // Монитора у сервера нет: секцию выбора монитора общее окно прячет.
        public int? MonitorIndex => null;
        // Порт дашборда: строку «Адрес для экранов» собирает общее окно через
        // KioskAddress.ForPort, сервер своего адреса не строит.
        public int? KioskPort => _config.Port;
        public bool WindowsAutostart => _config.AutoStart;
        public bool AutoLaunchOnSecondMonitor => false;

        // monitorIndex и autoLaunchOnSecondMonitor — настройки экрана киоска,
        // сервер их игнорирует.
        public void Save(string? url, string? excelPath, string? opcua, bool simulation,
                         bool lanAccess, int? monitorIndex, bool windowsAutostart,
                         bool autoLaunchOnSecondMonitor)
        {
            _config.ExcelPath = excelPath ?? _config.ExcelPath;
            _config.OpcuaEndpoint = opcua ?? _config.OpcuaEndpoint;
            _config.SimulationEnabled = simulation;
            _config.LanAccess = lanAccess;
            _config.AutoStart = windowsAutostart;
            try
            {
                _config.Save();
            }
            catch (Exception ex)
            {
                throw new InvalidOperationException("не удалось записать server_config.json: " + ex.Message, ex);
            }
            WindowsAutoStart.Apply(_config.AutoStart, WindowsAutoStart.ServerValueName, WindowsAutoStart.ServerArgsSuffix);
        }
    }

    // === Контекст сервера: backend → готовность → трей (без экрана киоска) ===
    sealed class ServerContext : ApplicationContext, ISettingsHost
    {
        private readonly ServerConfig _config;
        private readonly int _autoExitAfterReady;
        private readonly int _crashAfterReady;
        private readonly bool _silent;
        // Куда пишем автозапуск: null = настоящий Run, иначе тестовый подключ.
        private readonly string? _runKeyPath;
        private readonly RotatingLogger _appLog;
        private readonly RotatingLogger _backendLog;
        // Единственный владелец дочерних процессов: create → assign → stop.
        private readonly ChildProcesses _children;
        private readonly CancellationTokenSource _cts = new();

        private NotifyIcon? _tray;
        private Process? _backend;
        // Крючок smoke: процесс-заглушка после готовности сервера.
        private Process? _afterReady;
        private SettingsForm? _settingsForm;
        private bool _shutdownStarted;
        private UpdateInfo? _pendingUpdate;
        private System.Threading.Timer? _updateTimer;
        private string _updateStatus = "Нажмите «Проверить обновления».";

        public string UpdateStatus => _updateStatus;
        public bool HasPendingUpdate => _pendingUpdate != null;

        public int ExitCode { get; private set; }

        public ServerContext(ServerConfig config, int autoExitAfterReady, int crashAfterReady,
                             bool silent, string? runKeyPath = null)
        {
            _config = config;
            _autoExitAfterReady = autoExitAfterReady;
            _crashAfterReady = crashAfterReady;
            _silent = silent;
            // Тестовое подключение реестра для smoke (--run-key=<subkey>);
            // null — настоящий HKCU\...\Run.
            _runKeyPath = runKeyPath;
            _appLog = new RotatingLogger("server");
            _backendLog = new RotatingLogger("backend");
            _children = new ChildProcesses(_appLog);
            Current = this;
            _appLog.Write($"config: python={config.PythonExe} dir={config.BackendDir} " +
                $"args={config.ResolvedBackendArgs} kioskAddress={config.KioskAddress}");
            _appLog.Write($"settings: excel={config.ExcelPath} opcua={config.OpcuaEndpoint} " +
                $"sim={config.SimulationEnabled} lan={config.LanAccess} autostart={config.AutoStart}");
            SyncAutoStart();
            // Миграция: прежняя поставка (EkranchikAllInOne) больше не
            // поставляется — его значение автозапуска убираем, иначе при
            // автозагрузке стартует то, чего уже нет на диске. Значение
            // экрана киоска (Ekranchik) НЕ трогаем: это отдельное приложение.
            try
            {
                WindowsAutoStart.DeleteValue(WindowsAutoStart.LegacyAutostartValueName, _runKeyPath);
                _appLog.Write($"migration: legacy autostart value removed from " +
                              $"{WindowsAutoStart.EffectiveKeyPath(_runKeyPath)}");
            }
            catch (Exception ex)
            {
                _appLog.Write($"migration failed: {ex.Message}");
            }

            try
            {
                CreateTray();
            }
            catch (Exception ex)
            {
                // Без трея (headless) продолжаем: остановка — через Shutdown().
                _appLog.Write($"tray unavailable, continuing headless: {ex.Message}");
            }

            if (_silent)
                _appLog.Write("starting silent (no settings window)");
            else
                ShowSettings();

            Task.Run(() => StartupSequenceAsync(_cts.Token));
            _updateTimer = new System.Threading.Timer(
                _ => { Task.Run(() => CheckForUpdatesAsync(manual: false)); },
                null, TimeSpan.FromSeconds(30), UpdateChecker.Period);
        }

        // Желаемое состояние автозапуска из конфига → реестр (идемпотентно).
        private void SyncAutoStart()
        {
            try
            {
                WindowsAutoStart.Apply(_config.AutoStart, WindowsAutoStart.ServerValueName,
                                       WindowsAutoStart.ServerArgsSuffix, _runKeyPath);
                _appLog.Write($"autostart synced: {(_config.AutoStart ? "enabled" : "disabled")}");
            }
            catch (Exception ex)
            {
                _appLog.Write($"autostart sync failed: {ex.Message}");
            }
        }

        private void ShowSettings()
        {
            try
            {
                if (_settingsForm != null && !_settingsForm.IsDisposed)
                {
                    _settingsForm.Activate();
                    return;
                }
                _settingsForm = new SettingsForm(new ServerSettingsModel(_config), this);
                _settingsForm.FormClosed += (s, e) => { _settingsForm = null; };
                _settingsForm.Show();
            }
            catch (Exception ex)
            {
                _appLog.Write($"settings window failed: {ex.Message}");
            }
        }

        // --- Трей сервера: только действия, без портов и статусов. Экрана
        // киоска у сервера нет, поэтому и пунктов «монитор»/«режим простоя»
        // здесь не бывает — они в трее экрана (Ekranchik.exe). ---
        private void CreateTray()
        {
            var menu = new ContextMenuStrip();
            menu.Items.Add(new ToolStripMenuItem("⚙️ Настройки", null, (s, e) => ShowSettings()));
            menu.Items.Add(new ToolStripSeparator());
            menu.Items.Add(new ToolStripMenuItem("Выход", null, (s, e) => Shutdown("tray exit")));

            _tray = new NotifyIcon
            {
                Text = "Ekranchik — сервер",
                ContextMenuStrip = menu,
                Visible = true
            };
            try { _tray.Icon = Icon.ExtractAssociatedIcon(Application.ExecutablePath); }
            catch { _tray.Icon = SystemIcons.Application; }
            // Клик по иконке — открыть настройки: своего окна у сервера нет.
            _tray.MouseClick += (s, e) =>
            {
                if (e.Button == MouseButtons.Left) ShowSettings();
            };
            _tray.BalloonTipClicked += (s, e) => { Task.Run(() => InstallUpdateAsync()); };
        }

        public void OpenLogsFolder()
        {
            try
            {
                Process.Start(new ProcessStartInfo
                {
                    FileName = _appLog.LogDir,
                    UseShellExecute = true
                });
            }
            catch (Exception ex)
            {
                _appLog.Write($"open logs folder failed: {ex.Message}");
            }
        }

        // --- Последовательность запуска: сервер поднялся — и всё. Экрана
        // киоска здесь нет (отдельное приложение), остаётся smoke-хук. ---
        private async Task StartupSequenceAsync(CancellationToken token)
        {
            if (!StartBackend()) return;
            bool ready = await WaitForReadyAsync(token);
            if (!ready) return;
            StartAfterReadyHook();

            // Крючок smoke: жёсткая смерть без managed-очистки. Shutdown в этом
            // пути не бежит, поэтому детей может добить только job-объект.
            if (_crashAfterReady > 0)
            {
                _appLog.Write($"smoke hook: hard kill in {_crashAfterReady}s (no cleanup)");
                try { await Task.Delay(TimeSpan.FromSeconds(_crashAfterReady), token); } catch { }
                _appLog.Write("smoke hook: Process.Kill");
                Process.GetCurrentProcess().Kill();
                return;
            }

            if (_autoExitAfterReady > 0)
            {
                _appLog.Write($"smoke hook: auto-exit in {_autoExitAfterReady}s");
                try { await Task.Delay(TimeSpan.FromSeconds(_autoExitAfterReady), token); } catch { }
                Shutdown("auto-exit hook");
            }
        }

        private bool StartBackend()
        {
            try
            {
                if (!Directory.Exists(_config.BackendDir))
                {
                    Fail($"backend dir not found: {_config.BackendDir}");
                    return false;
                }
                var psi = new ProcessStartInfo
                {
                    FileName = _config.PythonExe,
                    Arguments = _config.ResolvedBackendArgs,
                    WorkingDirectory = _config.BackendDir,
                    UseShellExecute = false,
                    RedirectStandardOutput = true,
                    RedirectStandardError = true,
                    CreateNoWindow = true
                };
                // Issue #4: Excel/OPC UA/симуляция из окна настроек → env сервера.
                _config.ApplyToBackendEnvironment(psi.Environment);
                var proc = _children.Start(psi, ChildLifetime.Job, "backend", p =>
                {
                    p.EnableRaisingEvents = true;
                    p.OutputDataReceived += (s, e) => { if (e.Data != null) _backendLog.Write("[out] " + e.Data); };
                    p.ErrorDataReceived += (s, e) => { if (e.Data != null) _backendLog.Write("[err] " + e.Data); };
                    p.Exited += (s, e) =>
                    {
                        _backendLog.Write($"backend exited code={p.ExitCode}");
                        if (!_shutdownStarted && !_cts.IsCancellationRequested)
                            Fail($"backend exited early with code {p.ExitCode}, see backend log"
                                 + PythonLaunchHint() + PortHint());
                    };
                });
                if (proc == null)
                {
                    Fail("failed to start backend process");
                    return false;
                }

                proc.BeginOutputReadLine();
                proc.BeginErrorReadLine();
                _backend = proc;
                return true;
            }
            catch (Exception ex)
            {
                Fail($"failed to start backend: {ex.Message}");
                return false;
            }
        }

        // Подсказка к фатальному сообщению. Интерпретатор берётся из пакета
        // (python\ рядом с exe, dist-full\ в репозитории); если не нашёлся ни
        // один — подставляется системный python, а он без зависимостей бэкенда,
        // и uvicorn падает с кодом 1. Пользователь должен понять, чего не хватило.
        private string PythonLaunchHint()
        {
            string python = _config.PythonExe;
            if (Path.IsPathRooted(python)) return "\n\nPython: " + python;
            return "\n\nPython: " + python + " — системный; ни python\\ рядом с exe," +
                   " ни dist-full\\python\\ в репозитории не найдено." +
                   "\nЛибо переустанови EkranchikSetup.exe (тип «Сервер: фоновое приложение»)" +
                   " и запусти ярлык «Ekranchik (сервер)», либо собери пакет:" +
                   " scripts\\build-full-package.ps1";
        }

        // Порт занят — самая частая причина раннего падения бэкенда: уже
        // запущен другой экземпляр сервера Ekranchik (или сторонняя программа).
        // Проверяем фактом: если сокет не поднялся — место действительно занято.
        private string PortHint()
        {
            try
            {
                var probe = new System.Net.Sockets.TcpListener(
                    System.Net.IPAddress.Loopback, _config.Port);
                probe.Start();
                probe.Stop();
                return "";
            }
            catch (System.Net.Sockets.SocketException)
            {
                return $"\n\nПорт {_config.Port} уже занят другим процессом — обычно это второй" +
                       " экземпляр сервера Ekranchik: закройте его (значок в трее → «Выход»)" +
                       " и запустите снова.";
            }
        }

        private async Task<bool> WaitForReadyAsync(CancellationToken token)
        {
            string healthUrl = _config.ResolvedDashboardUrl.TrimEnd('/') + "/health";
            var deadline = DateTime.UtcNow.AddSeconds(_config.ReadyTimeoutSeconds);
            using var http = new HttpClient { Timeout = TimeSpan.FromSeconds(5) };
            _appLog.Write($"waiting for {healthUrl} (timeout {_config.ReadyTimeoutSeconds}s)");
            // Причина последней неудачи — в лог: без неё «не дождались» нечем
            // объяснить оператору, кроме молчаливого выхода.
            string lastError = "нет ответа";
            while (DateTime.UtcNow < deadline && !token.IsCancellationRequested)
            {
                if (_backend is { HasExited: true })
                    return false; // Fail() уже вызван из Exited
                try
                {
                    using var resp = await http.GetAsync(healthUrl, token);
                    if (resp.IsSuccessStatusCode)
                    {
                        _appLog.Write("backend ready");
                        return true;
                    }
                    lastError = $"HTTP {(int)resp.StatusCode}";
                }
                // Отмена по таймауту HttpClient — это TaskCanceledException,
                // наследник OperationCanceledException: медленный ответ на /health
                // не значит «сервер не поднимется». Различаем отмену задачи и
                // отмену запроса, иначе старт молча прерывался на первом же
                // небыстром ответе.
                catch (OperationCanceledException) when (token.IsCancellationRequested) { return false; }
                catch (Exception ex) { lastError = ex.Message; }
                try { await Task.Delay(1000, token); } catch { return false; }
            }
            if (!token.IsCancellationRequested)
                Fail($"backend not ready in {_config.ReadyTimeoutSeconds}s: {healthUrl}" +
                     $" (последняя причина: {lastError})");
            return false;
        }

        // Крючок smoke: процесс-заглушка после готовности сервера. Живёт
        // столько же, сколько сервер, и умирает вместе с ним (job-объект).
        private void StartAfterReadyHook()
        {
            if (string.IsNullOrWhiteSpace(_config.AfterReadyExe)) return;
            try
            {
                var psi = new ProcessStartInfo
                {
                    FileName = _config.AfterReadyExe,
                    Arguments = _config.AfterReadyArgs,
                    UseShellExecute = false,
                    CreateNoWindow = true
                };
                _afterReady = _children.Start(psi, ChildLifetime.Job, "after-ready");
                // ChildProcesses уже пишет строку запуска с pid — здесь только
                // итог для оператора: заглушка жива или нет.
                if (_afterReady == null)
                    _appLog.Write("after-ready hook not started (server keeps running)");
            }
            catch (Exception ex)
            {
                _appLog.Write($"after-ready hook failed: {ex.Message}");
            }
        }

        private void Fail(string message)
        {
            _appLog.Write("FATAL: " + message);
            ExitCode = 1;
            // В тихом режиме (--silent/автозапуск) — только лог, без окна:
            // модалка блокировала бы Shutdown и вешала процесс без видимого UI.
            if (!_silent)
            {
                try
                {
                    MessageBox.Show(message + "\n\nПодробности — в папке логов Ekranchik.",
                        "Ekranchik (сервер)", MessageBoxButtons.OK, MessageBoxIcon.Error);
                }
                catch { }
            }
            Shutdown("fatal");
        }

        // Экрана киоска у сервера нет: встроенной формы не гасим, только
        // дочерние процессы (StopChildren выше).

        // --- Остановка: один путь и для трея «Выход», и для smoke-хука ---
        private void Shutdown(string reason)
        {
            if (_shutdownStarted) return;
            _shutdownStarted = true;
            _appLog.Write($"shutdown ({reason})");
            try { _cts.Cancel(); } catch { }
            try { _updateTimer?.Dispose(); } catch { }

            StopChildren();

            try
            {
                if (_tray != null)
                {
                    _tray.Visible = false;
                    _tray.Dispose();
                    _tray = null;
                }
            }
            catch { }

            _appLog.Write("stopped");
            _appLog.Dispose();
            _backendLog.Dispose();
            ExitThread();
        }

        // Дети, которыми владеет приложение. Установщик обновления стартует как
        // Detached и здесь намеренно не трогается.
        private void StopChildren()
        {
            _children.Stop(_afterReady, "after-ready");
            _children.Stop(_backend, "backend");
        }

        // === Обновления: канал full-v* + ассет EkranchikSetup.exe ===
        // Проверка: старт (+30с) + раз в 6ч + пункт трея. Без сети — тихий фейл.
        public async Task CheckForUpdatesAsync(bool manual)
        {
            UpdateInfo? update = await UpdateChecker.CheckForUpdateAsync(
                AppVersion.Current, UpdateChecker.FullChannelPrefix, "EkranchikSetup.exe").ConfigureAwait(false);
            if (update == null)
            {
                _updateStatus = "У вас последняя версия.";
                _appLog.Write("update check: no updates");
                if (manual)
                    Notify("Ekranchik: у вас последняя версия.");
            }
            else
            {
                _pendingUpdate = update;
                _updateStatus = $"Доступна версия {update.Version} (текущая {AppVersion.Current}).";
                _appLog.Write($"update available: {update.Tag}");
                Notify($"Доступна версия {update.Version}. Нажмите, чтобы установить.");
            }
            RefreshOpenSettings();
        }

        // Обновление в клик: скачать Setup во tmp → остановить дочерние процессы →
        // запустить Setup → корректно завершить себя.
        public async Task InstallUpdateAsync()
        {
            UpdateInfo? update = _pendingUpdate;
            if (update == null)
                return;
            _updateStatus = "Скачивание обновления...";
            RefreshOpenSettings();
            Notify("Ekranchik: скачивание обновления...");
            string setupPath;
            try
            {
                setupPath = await UpdateChecker.DownloadAssetAsync(update).ConfigureAwait(false);
                _appLog.Write($"update downloaded: {setupPath}");
            }
            catch (Exception ex)
            {
                _updateStatus = "Не удалось скачать обновление.";
                _appLog.Write($"update download failed: {ex.Message}");
                Notify("Ekranchik: не удалось скачать обновление.");
                RefreshOpenSettings();
                return;
            }
            _updateStatus = "Установка обновления...";
            RefreshOpenSettings();
            try
            {
                StopChildren();
                // Экрана киоска у сервера нет — гасим только дочерние процессы.
            }
            catch (Exception ex)
            {
                _appLog.Write($"update stop children failed: {ex.Message}");
            }
            // Установщик обязан пережить нас — Detached: ни job, ни Stop.
            if (_children.Start(
                    new ProcessStartInfo { FileName = setupPath, UseShellExecute = true },
                    ChildLifetime.Detached, "setup") == null)
            {
                _updateStatus = "Не удалось запустить установщик.";
                _appLog.Write($"setup launch failed: {setupPath}");
                Notify("Ekranchik: не удалось запустить установщик.");
                RefreshOpenSettings();
                return;
            }
            _appLog.Write($"setup launched: {setupPath}");
            Shutdown("update");
        }

        // Фоновая находка освежает открытое окно настроек (P3-7).
        private void RefreshOpenSettings()
        {
            try
            {
                var form = _settingsForm;
                if (form != null && !form.IsDisposed && form.IsHandleCreated)
                    form.BeginInvoke(new Action(() => { if (!form.IsDisposed) form.RefreshFromUpdater(); }));
            }
            catch { }
        }

        private void Notify(string text)
        {
            try
            {
                if (_tray != null)
                    _tray.ShowBalloonTip(10000, "Ekranchik", text, ToolTipIcon.Info);
                else
                    _appLog.Write("notify: " + text);
            }
            catch (Exception ex)
            {
                _appLog.Write("notify failed: " + ex.Message);
            }
        }

        public string VersionsText(string backendVersion)
        {
            return $"Сервер: {AppVersion.Current}\nBackend: {backendVersion}";
        }

        public async Task<string> GetBackendVersionAsync()
        {
            try
            {
                string url = _config.ResolvedDashboardUrl.TrimEnd('/') + "/api/version";
                using var http = new HttpClient { Timeout = TimeSpan.FromSeconds(3) };
                string json = await http.GetStringAsync(url).ConfigureAwait(false);
                using JsonDocument doc = JsonDocument.Parse(json);
                if (doc.RootElement.TryGetProperty("version", out JsonElement v))
                    return v.GetString() ?? "—";
            }
            catch { }
            return "—";
        }

        // Крэш-хендлеры (issue #9): падение UI-потока больше не роняет стек
        // молча — лог + корректная остановка (job-объект в ChildProcesses
        // добивает backend, если Shutdown не дойдёт).
        private static ServerContext? Current;
        public static void ReportUiCrash(Exception ex)
        {
            Current?.CrashStop("ui thread exception: " + ex.Message);
        }

        public static void ReportCrash(object? unhandled)
        {
            if (unhandled is Exception ex)
                Current?.CrashStop("appdomain exception: " + ex.Message);
        }

        private void CrashStop(string what)
        {
            if (_shutdownStarted) return;
            _appLog.Write("FATAL: " + what);
            ExitCode = 1;
            Shutdown("crash");
        }

        // Окно настроек сохранило. Экрана у сервера нет, поэтому настроек
        // киоска тут нечего применять: конфиг и реестр уже записаны моделью.
        public void OnSettingsSaved()
        {
            _appLog.Write("settings saved: " +
                $"excel={_config.ExcelPath} opcua={_config.OpcuaEndpoint} " +
                $"sim={_config.SimulationEnabled} lan={_config.LanAccess} " +
                $"port={_config.Port} autostart={_config.AutoStart}");
        }

        protected override void Dispose(bool disposing)
        {
            if (disposing)
            {
                try { _cts.Dispose(); } catch { }
                try { _updateTimer?.Dispose(); } catch { }
                try { _backend?.Dispose(); } catch { }
                try { _afterReady?.Dispose(); } catch { }
            }
            base.Dispose(disposing);
        }
    }
}
