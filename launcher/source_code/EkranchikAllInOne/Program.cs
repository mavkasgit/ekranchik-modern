// EkranchikAllInOne — трей-лаунчер полного режима (issue #3, ADR 0002; окно
// настроек + автозапуск Windows — issue #4).
//
// Сценарий: двойной клик → окно настроек (Excel, OPC UA, симуляция, монитор,
// автозапуск) → запуск backend (python -m uvicorn) → poll /health →
// запуск существующего Ekranchik.exe с URL дашборда → трей с «Настройки» /
// «Открыть папку логов» / «Выход» (останавливает сервер и закрывает киоск).
// Флаг --silent (и запись автозапуска HKCU ...\Run с ним): старт в трей без
// окна, стек поднимается сам.
//
// Конфигурирование: JSON %LOCALAPPDATA%/Ekranchik/allinone_config.json
// + перекрывающие env-переменные EKRANCHIK_* (см. AllInOneConfig).
// В трее НЕТ портов/статусов — только действия.
//
// Тестовые крючки для smoke (не показываются пользователю):
//   --auto-exit-after-ready=N — после успешного запуска киоска ждёт N сек и
//     идёт по ТОМУ ЖЕ коду Shutdown(), что и пункт трея «Выход»;
//     подразумевает тихий режим (без окна настроек);
//   --dump-config — печатает итоговый конфиг (файл + env) в stdout и выходит;
//   --autostart=on|off [--run-key=<subkey>] — включает/выключает автозапуск
//     (по умолчанию в настоящем Run; с --run-key — в тестовом подключе
//     HKCU\<subkey> под тем же именем значения) и выходит.

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

namespace EkranchikAllInOne
{
    static class Program
    {
        [STAThread]
        static int Main(string[] args)
        {
            Application.EnableVisualStyles();
            Application.SetCompatibleTextRenderingDefault(false);
            // Падение UI-потока больше не роняет весь стек (issue #9):
            // лог + корректная остановка сервера и трея. Режим ставится ДО
            // создания скрытых контролов синхронизации.
            Application.SetUnhandledExceptionMode(UnhandledExceptionMode.CatchException);
            Application.ThreadException += (s, e) => AllInOneContext.ReportUiCrash(e.Exception);
            AppDomain.CurrentDomain.UnhandledException += (s, e) => AllInOneContext.ReportCrash(e.ExceptionObject);
            // Контекст синхронизации UI-потока: окно киоска создаётся только
            // на Main-потоке (issue #9).
            SynchronizationContext.SetSynchronizationContext(new WindowsFormsSynchronizationContext());

            int autoExitAfterReady = 0;
            bool silent = false;
            bool dumpConfig = false;
            bool selfTest = false;
            string? autostartArg = null;
            string? runKeyArg = null;
            foreach (var arg in args)
            {
                const string autoPrefix = "--auto-exit-after-ready=";
                const string autostartPrefix = "--autostart=";
                const string runKeyPrefix = "--run-key=";
                if (arg.StartsWith(autoPrefix, StringComparison.OrdinalIgnoreCase)
                    && int.TryParse(arg.Substring(autoPrefix.Length), out int seconds)
                    && seconds > 0)
                {
                    autoExitAfterReady = seconds;
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
                    WindowsAutoStart.Apply(enable, WindowsAutoStart.AllInOneValueName, WindowsAutoStart.AllInOneArgsSuffix, runKeyArg);
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

            var config = AllInOneConfig.Load();

            // Крючок smoke: проверка persist пяти настроек (файл + env).
            if (dumpConfig)
            {
                Console.WriteLine(JsonSerializer.Serialize(config,
                    new JsonSerializerOptions { WriteIndented = false }));
                return 0;
            }

            // smoke-хук идёт тем же тихим путём, что и --silent: без окна.
            using (var context = new AllInOneContext(config, autoExitAfterReady, silent || autoExitAfterReady > 0))
            {
                Application.Run(context);
                return context.ExitCode;
            }
        }
    }

    // === Конфигурация (JSON + env-переопределения). Issue #4: пять настроек
    // окна (путь Excel, адрес OPC UA, симуляция, монитор киоска, автозапуск)
    // persist-ятся в allinone_config.json между запусками. ===
    sealed class AllInOneConfig
    {
        public string PythonExe { get; set; } = "python";
        // Полная строка аргументов backend; {port} подставляется автоматически.
        public string BackendArgs { get; set; } = "-m uvicorn app.main:app --host 127.0.0.1 --port {port}";
        public string BackendDir { get; set; } = "";
        public int Port { get; set; } = 8083;
        public string DashboardUrl { get; set; } = "";
        public string KioskExe { get; set; } = "";
        // Крючок smoke/дев: киоск запускается внешним процессом, а не окном
        // в этом же процессе. Ставится только env EKRANCHIK_KIOSK_EXE.
        public bool UseExternalKiosk { get; private set; } = false;
        // Полная строка аргументов киоска; {url} подставляется автоматически.
        public string KioskArgs { get; set; } = "--no-gui \"{url}\"";
        public int ReadyTimeoutSeconds { get; set; } = 90;

        // --- Issue #4: настройки окна (persist между запусками) ---
        // Сетевой путь к Excel-книге учёта.
        public string ExcelPath { get; set; } = "//ktm-disk/Оператор/Учет КПЗ 2026.xlsm";
        // Адрес реального OPC UA сервера.
        public string OpcuaEndpoint { get; set; } = "opc.tcp://172.17.11.131:4840/";
        // Тестовые данные (SIMULATION_ENABLED у backend).
        public bool SimulationEnabled { get; set; } = false;
        // Индекс монитора для киоска (как monitor в kiosk_config.json).
        public int KioskMonitor { get; set; } = 0;
        // Желаемый автозапуск Windows (реестр HKCU ...\Run синхронизируется
        // при старте и при сохранении окна настроек).
        public bool AutoStart { get; set; } = false;
        private static readonly string ConfigDir = Path.Combine(
            Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData), "Ekranchik");
        private static readonly string ConfigFile = Path.Combine(ConfigDir, "allinone_config.json");

        public string ResolvedBackendArgs => BackendArgs.Replace("{port}", Port.ToString());

        public string ResolvedDashboardUrl =>
            string.IsNullOrWhiteSpace(DashboardUrl) ? $"http://localhost:{Port}" : DashboardUrl;
        public string ResolvedKioskArgs =>
            KioskArgs.Replace("{url}", ResolvedDashboardUrl);

        public static AllInOneConfig Load()
        {
            var config = new AllInOneConfig();
            if (File.Exists(ConfigFile))
            {
                try
                {
                    var loaded = JsonSerializer.Deserialize<AllInOneConfig>(File.ReadAllText(ConfigFile));
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
            if (!string.IsNullOrWhiteSpace(Env("EKRANCHIK_KIOSK_EXE")))
            {
                KioskExe = Env("EKRANCHIK_KIOSK_EXE")!;
                UseExternalKiosk = true;
            }
            if (!string.IsNullOrWhiteSpace(Env("EKRANCHIK_KIOSK_ARGS"))) KioskArgs = Env("EKRANCHIK_KIOSK_ARGS")!;
            if (!string.IsNullOrWhiteSpace(Env("EKRANCHIK_URL"))) DashboardUrl = Env("EKRANCHIK_URL")!;
            if (!string.IsNullOrWhiteSpace(Env("EKRANCHIK_EXCEL_PATH"))) ExcelPath = Env("EKRANCHIK_EXCEL_PATH")!;
            if (!string.IsNullOrWhiteSpace(Env("EKRANCHIK_OPCUA_ENDPOINT"))) OpcuaEndpoint = Env("EKRANCHIK_OPCUA_ENDPOINT")!;
            if (TryParseBool(Env("EKRANCHIK_SIMULATION"), out bool sim)) SimulationEnabled = sim;
            if (int.TryParse(Env("EKRANCHIK_KIOSK_MONITOR"), out int monitor) && monitor >= 0) KioskMonitor = monitor;
            if (TryParseBool(Env("EKRANCHIK_AUTOSTART"), out bool autostart)) AutoStart = autostart;
            if (int.TryParse(Env("EKRANCHIK_PORT"), out int port) && port > 0 && port < 65536) Port = port;
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
            if (string.IsNullOrWhiteSpace(BackendDir))
                BackendDir = ResolveBackendDir(exeDir);
            if (string.IsNullOrWhiteSpace(KioskExe))
                KioskExe = Path.Combine(exeDir, "Ekranchik.exe");
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

    // === Модель настроек полного режима для единого окна (issue #9):
    // обёртка AllInOneConfig. URL-поле скрыто (URL — всегда локальный
    // сервер), серверная секция видна. ===
    sealed class AllInOneSettingsModel : ISettingsModel
    {
        private readonly AllInOneConfig _config;

        public AllInOneSettingsModel(AllInOneConfig config)
        {
            _config = config;
        }

        public string? Url => null;
        public string? ExcelPath => _config.ExcelPath;
        public string? OpcuaEndpoint => _config.OpcuaEndpoint;
        public bool Simulation => _config.SimulationEnabled;
        public int MonitorIndex => _config.KioskMonitor;
        public bool WindowsAutostart => _config.AutoStart;
        public bool AutoLaunchOnSecondMonitor => false;

        public void Save(string? url, string? excelPath, string? opcua, bool simulation,
                         int monitorIndex, bool windowsAutostart, bool autoLaunchOnSecondMonitor)
        {
            _config.ExcelPath = excelPath ?? _config.ExcelPath;
            _config.OpcuaEndpoint = opcua ?? _config.OpcuaEndpoint;
            _config.SimulationEnabled = simulation;
            _config.KioskMonitor = Math.Max(monitorIndex, 0);
            _config.AutoStart = windowsAutostart;
            try
            {
                _config.Save();
            }
            catch (Exception ex)
            {
                throw new InvalidOperationException("не удалось записать allinone_config.json: " + ex.Message, ex);
            }
            WindowsAutoStart.Apply(_config.AutoStart, WindowsAutoStart.AllInOneValueName, WindowsAutoStart.AllInOneArgsSuffix);
        }
    }

    // === Контекст приложения: backend → готовность → киоск → трей ===
    sealed class AllInOneContext : ApplicationContext, IKioskHost, ISettingsHost
    {
        private readonly AllInOneConfig _config;
        private readonly int _autoExitAfterReady;
        private readonly bool _silent;
        private readonly RotatingLogger _appLog;
        private readonly RotatingLogger _backendLog;
        private readonly CancellationTokenSource _cts = new();
        // UI-поток: Main ставит WindowsFormsSynchronizationContext, контекст
        // захватывается на UI-потоке; окно киоска создаётся только через Post.
        private readonly SynchronizationContext? _ui;

        private NotifyIcon? _tray;
        private ToolStripMenuItem? _idleItem;
        private Process? _backend;
        private Process? _kiosk;
        // Киоск в этом же процессе (issue #9); _kiosk остаётся для крючка
        // smoke (внешний процесс).
        private KioskForm? _kioskForm;
        private SettingsForm? _settingsForm;
        private bool _shutdownStarted;
        private UpdateInfo? _pendingUpdate;
        private System.Threading.Timer? _updateTimer;
        private string _updateStatus = "Нажмите «Проверить обновления».";

        public string UpdateStatus => _updateStatus;
        public bool HasPendingUpdate => _pendingUpdate != null;

        public int ExitCode { get; private set; }

        public AllInOneContext(AllInOneConfig config, int autoExitAfterReady, bool silent)
        {
            _config = config;
            _autoExitAfterReady = autoExitAfterReady;
            _silent = silent;
            _appLog = new RotatingLogger("allinone");
            _backendLog = new RotatingLogger("backend");
            Current = this;
            _ui = SynchronizationContext.Current;
            if (_ui == null)
                _appLog.Write("WARN: no UI SynchronizationContext — kiosk window will not start");
            _appLog.Write($"config: python={config.PythonExe} dir={config.BackendDir} " +
                $"args={config.ResolvedBackendArgs} url={config.ResolvedDashboardUrl} kiosk={config.KioskExe}");
            _appLog.Write($"settings: excel={config.ExcelPath} opcua={config.OpcuaEndpoint} " +
                $"sim={config.SimulationEnabled} monitor={config.KioskMonitor} autostart={config.AutoStart}");
            SyncAutoStart();
            // Миграция (issue #9): старое киоск-значение автозапуска больше
            // не нужно — полный режим стартует одним приложением.
            try
            {
                WindowsAutoStart.DeleteValue(WindowsAutoStart.KioskValueName);
                _appLog.Write("migration: legacy kiosk autostart value removed");
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
                WindowsAutoStart.Apply(_config.AutoStart, WindowsAutoStart.AllInOneValueName, WindowsAutoStart.AllInOneArgsSuffix);
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
                _settingsForm = new SettingsForm(new AllInOneSettingsModel(_config), this);
                _settingsForm.FormClosed += (s, e) => { _settingsForm = null; };
                _settingsForm.Show();
            }
            catch (Exception ex)
            {
                _appLog.Write($"settings window failed: {ex.Message}");
            }
        }

        // --- Трей: меню киоска как было (issue #9), никаких портов/статусов ---
        private void CreateTray()
        {
            var menu = new ContextMenuStrip();
            menu.Items.Add(new ToolStripMenuItem("Переключить монитор", null, (s, e) => _kioskForm?.SwitchMonitor()));
            _idleItem = new ToolStripMenuItem("🕐 Режим простоя", null, (s, e) => _kioskForm?.ToggleIdleScreen());
            menu.Items.Add(_idleItem);
            menu.Items.Add(new ToolStripMenuItem("⚙️ Настройки", null, (s, e) => ShowSettings()));
            menu.Items.Add(new ToolStripMenuItem("🔄 Проверить обновления", null, (s, e) => { Task.Run(() => CheckForUpdatesAsync(manual: true)); }));
            menu.Items.Add(new ToolStripSeparator());
            menu.Items.Add(new ToolStripMenuItem("Выход", null, (s, e) => Shutdown("tray exit")));

            _tray = new NotifyIcon
            {
                Text = "Ekranchik",
                ContextMenuStrip = menu,
                Visible = true
            };
            try { _tray.Icon = Icon.ExtractAssociatedIcon(Application.ExecutablePath); }
            catch { _tray.Icon = SystemIcons.Application; }
            // Клик по иконке — вернуть спрятанный экран (issue #9).
            _tray.MouseClick += (s, e) =>
            {
                if (e.Button == MouseButtons.Left) ShowKioskWindow();
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

        // --- Последовательность запуска ---
        private async Task StartupSequenceAsync(CancellationToken token)
        {
            if (!StartBackend()) return;
            bool ready = await WaitForReadyAsync(token);
            if (!ready) return;
            StartKiosk();

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
                var proc = new Process { StartInfo = psi, EnableRaisingEvents = true };
                proc.OutputDataReceived += (s, e) => { if (e.Data != null) _backendLog.Write("[out] " + e.Data); };
                proc.ErrorDataReceived += (s, e) => { if (e.Data != null) _backendLog.Write("[err] " + e.Data); };
                proc.Exited += (s, e) =>
                {
                    _backendLog.Write($"backend exited code={proc.ExitCode}");
                    if (!_shutdownStarted && !_cts.IsCancellationRequested)
                        Fail($"backend exited early with code {proc.ExitCode}, see backend log");
                };
                if (!proc.Start())
                {
                    Fail("failed to start backend process");
                    return false;
                }
                proc.BeginOutputReadLine();
                proc.BeginErrorReadLine();
                _backend = proc;
                _appLog.Write($"backend started pid={proc.Id}");
                return true;
            }
            catch (Exception ex)
            {
                Fail($"failed to start backend: {ex.Message}");
                return false;
            }
        }

        private async Task<bool> WaitForReadyAsync(CancellationToken token)
        {
            string healthUrl = _config.ResolvedDashboardUrl.TrimEnd('/') + "/health";
            var deadline = DateTime.UtcNow.AddSeconds(_config.ReadyTimeoutSeconds);
            using var http = new HttpClient { Timeout = TimeSpan.FromSeconds(2) };
            _appLog.Write($"waiting for {healthUrl} (timeout {_config.ReadyTimeoutSeconds}s)");
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
                }
                catch (OperationCanceledException) { return false; }
                catch { /* ещё не готов — ждём */ }
                try { await Task.Delay(1000, token); } catch { return false; }
            }
            if (!token.IsCancellationRequested)
                Fail($"backend not ready in {_config.ReadyTimeoutSeconds}s: {healthUrl}");
            return false;
        }

        private void StartKiosk()
        {
            // Крючок smoke/дев: киоск — внешний процесс.
            if (_config.UseExternalKiosk)
            {
                try
                {
                    if (!File.Exists(_config.KioskExe))
                    {
                        _appLog.Write($"kiosk exe not found, skipping: {_config.KioskExe}");
                        return; // Сервер уже работает — отсутствие киоска не фатально.
                    }
                    PointKioskConfigAtDashboard();
                    // URL позиционным аргументом (киоск берёт URL из конфига,
                    // лишние аргументы игнорирует) + --no-gui против окна настроек.
                    var psi = new ProcessStartInfo
                    {
                        FileName = _config.KioskExe,
                        Arguments = _config.ResolvedKioskArgs,
                        UseShellExecute = false
                    };
                    _kiosk = Process.Start(psi);
                    ProcessJob.Assign(_kiosk);
                    _appLog.Write($"kiosk started pid={_kiosk?.Id}");
                }
                catch (Exception ex)
                {
                    _appLog.Write($"kiosk start failed (backend keeps running): {ex.Message}");
                }
                return;
            }

            // Полный режим (issue #9): экран киоска живёт в этом же процессе —
            // одно приложение, одна иконка в трее.
            PointKioskConfigAtDashboard();
            _ui?.Post(_ =>
            {
                try
                {
                    _kioskForm = new KioskForm(_config.ResolvedDashboardUrl, Math.Max(_config.KioskMonitor, 0), this);
                    _kioskForm.Show();
                    _appLog.Write("kiosk window shown (in-process)");
                }
                catch (Exception ex)
                {
                    _appLog.Write($"kiosk window failed (backend keeps running): {ex.Message}");
                }
            }, null);
        }

        // Киоск читает URL и монитор из kiosk_config.json — подменяем поля url
        // и monitor (issue #4: монитор из окна настроек), остальные настройки
        // (автозапуск киоска, неизвестные ключи) сохраняем как есть.
        // Безопасность записи:
        //   - целый конфиг → копия в kiosk_config.json.bak до изменения;
        //   - битый конфиг → копия в kiosk_config.corrupt-<ts>.bak, затем
        //     минимальный валидный конфиг (настройки уже не спасти, но киоск
        //     стартует, а исходник лежит в бэкапе);
        //   - запись через tmp-файл + move (не бывает полузаписанного конфига).
        // Восстановление исходника — НЕ здесь (в проде URL должен остаться),
        // а в smoke-хуке, который подменяет чужой конфиг на время прогона.
        private void PointKioskConfigAtDashboard()
        {
            try
            {
                string dir = Path.Combine(
                    Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData), "Ekranchik");
                Directory.CreateDirectory(dir);
                string file = Path.Combine(dir, "kiosk_config.json");
                Dictionary<string, JsonElement> root = new();
                if (File.Exists(file))
                {
                    string raw = File.ReadAllText(file);
                    try
                    {
                        var parsed = JsonSerializer.Deserialize<Dictionary<string, JsonElement>>(raw);
                        root = parsed ?? new Dictionary<string, JsonElement>();
                        File.Copy(file, file + ".bak", overwrite: true);
                    }
                    catch
                    {
                        string corruptBak = file + $".corrupt-{DateTime.Now:yyyyMMddHHmmss}.bak";
                        File.Copy(file, corruptBak);
                        _appLog.Write($"kiosk config corrupt, raw saved to {Path.GetFileName(corruptBak)}");
                    }
                }
                root["url"] = JsonDocument.Parse($"\"{_config.ResolvedDashboardUrl}\"").RootElement;
                int monitor = Math.Max(_config.KioskMonitor, 0);
                root["monitor"] = JsonDocument.Parse(monitor.ToString()).RootElement;
                string tmp = file + ".tmp";
                File.WriteAllText(tmp, JsonSerializer.Serialize(root,
                    new JsonSerializerOptions { WriteIndented = true }));
                File.Move(tmp, file, overwrite: true);
                _appLog.Write($"kiosk_config.json url+monitor updated (monitor={monitor})");
            }
            catch (Exception ex)
            {
                _appLog.Write($"kiosk config update failed: {ex.Message}");
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
                        "Ekranchik", MessageBoxButtons.OK, MessageBoxIcon.Error);
                }
                catch { }
            }
            Shutdown("fatal");
        }

        // Гасим встроенный экран на UI-потоке (issue #9): и при «Выход»,
        // и перед запуском установщика обновления.
        private void DisposeKioskForm()
        {
            try { _ui?.Post(_ => { try { _kioskForm?.Dispose(); } catch { } _kioskForm = null; }, null); } catch { }
        }

        // --- Остановка: один путь и для трея «Выход», и для smoke-хука ---
        private void Shutdown(string reason)
        {
            if (_shutdownStarted) return;
            _shutdownStarted = true;
            _appLog.Write($"shutdown ({reason})");
            try { _cts.Cancel(); } catch { }
            try { _updateTimer?.Dispose(); } catch { }

            StopProcess(_kiosk, "kiosk");
            StopProcess(_backend, "backend");
            // Встроенный экран живёт в этом процессе — закрываем форму
            // (внешний киоск — через StopProcess выше).
            DisposeKioskForm();

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

        private static void StopProcess(Process? proc, string name)
        {
            if (proc == null) return;
            try
            {
                if (proc.HasExited) return;
                try { proc.CloseMainWindow(); } catch { }
                if (!proc.WaitForExit(3000))
                {
                    try { proc.Kill(entireProcessTree: true); } catch { }
                    proc.WaitForExit(5000);
                }
            }
            catch { /* процесс уже мёртв — цель достигнута */ }
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
                StopProcess(_kiosk, "kiosk");
                StopProcess(_backend, "backend");
                // Встроенный экран гасим до запуска установщика (issue #9).
                DisposeKioskForm();
            }
            catch (Exception ex)
            {
                _appLog.Write($"update stop children failed: {ex.Message}");
            }
            try
            {
                Process.Start(new ProcessStartInfo { FileName = setupPath, UseShellExecute = true });
                _appLog.Write($"setup launched: {setupPath}");
            }
            catch (Exception ex)
            {
                _updateStatus = "Не удалось запустить установщик.";
                _appLog.Write($"setup launch failed: {ex.Message}");
                Notify("Ekranchik: не удалось запустить установщик.");
                RefreshOpenSettings();
                return;
            }
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
            return $"All-in-One: {AppVersion.Current}\nBackend: {backendVersion}";
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

        // === IKioskHost (issue #9): экран прячется в трей, пункт простоя
        // обновляется на UI-потоке. ===
        void IKioskHost.OnKioskCloseRequested()
        {
            _appLog.Write("kiosk close requested -> hide to tray");
            _ui?.Post(_ =>
            {
                try { if (_kioskForm is { IsDisposed: false }) _kioskForm.Hide(); } catch { }
            }, null);
        }

        void IKioskHost.OnIdleModeChanged(bool idle)
        {
            _appLog.Write($"idle mode: {idle}");
            _ui?.Post(_ =>
            {
                try { if (_idleItem != null) _idleItem.Text = idle ? "💻 Вернуться к работе" : "🕐 Режим простоя"; } catch { }
            }, null);
        }

        // Клик по иконке трея / кнопка «Показать экран» (issue #9).
        public void ShowKioskWindow()
        {
            if (_kioskForm == null || _kioskForm.IsDisposed)
            {
                _appLog.Write("show kiosk: window not created yet (backend not ready)");
                return;
            }
            _ui?.Post(_ =>
            {
                try
                {
                    if (_kioskForm is { IsDisposed: false })
                    {
                        _kioskForm.Show();
                        if (_kioskForm.WindowState == FormWindowState.Minimized)
                            _kioskForm.WindowState = FormWindowState.Normal;
                        _kioskForm.Activate();
                    }
                }
                catch (Exception ex) { _appLog.Write($"show kiosk failed: {ex.Message}"); }
            }, null);
        }

        // Крэш-хендлеры (issue #9): падение UI-потока больше не роняет стек
        // молча — лог + корректная остановка (Job Object чистит бэкенд).
        private static AllInOneContext? Current;
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
        // Окно настроек сохранило (issue #9): монитор сразу к живому экрану,
        // kiosk_config.json актуализируем для будущего перехода «только киоск».
        public void OnSettingsSaved()
        {
            PointKioskConfigAtDashboard();
            int monitor = Math.Max(_config.KioskMonitor, 0);
            _ui?.Post(_ =>
            {
                try
                {
                    if (_kioskForm is { IsDisposed: false })
                        _kioskForm.ApplyMonitor(monitor);
                }
                catch (Exception ex) { _appLog.Write($"apply monitor failed: {ex.Message}"); }
            }, null);
        }

        protected override void Dispose(bool disposing)
        {
            if (disposing)
            {
                try { _cts.Dispose(); } catch { }
                try { _updateTimer?.Dispose(); } catch { }
                try { _backend?.Dispose(); } catch { }
                try { _kiosk?.Dispose(); } catch { }
            }
            base.Dispose(disposing);
        }
    }
    // === Job Object (issue #9): дочерние процессы (python-бэкенд, внешний
    // киоск в крючке smoke) умирают вместе с приложением даже при аварийной
    // смерти процесса. Ошибка Job Object не фатальна: StopProcess в
    // Shutdown работает как раньше. ===
    static class ProcessJob
    {
        private static IntPtr _handle = IntPtr.Zero;
        private static readonly object _lock = new();
        private const int JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE = 0x2000;
        private const int JobObjectBasicLimitInformation = 4;

        [System.Runtime.InteropServices.StructLayout(System.Runtime.InteropServices.LayoutKind.Sequential)]
        private struct JOBOBJECT_BASIC_LIMIT_INFORMATION
        {
            public long PerProcessUserTimeLimit;
            public long PerJobUserTimeLimit;
            public uint LimitFlags;
            public UIntPtr MinimumWorkingSetSize;
            public UIntPtr MaximumWorkingSetSize;
            public uint ActiveProcessLimit;
            public UIntPtr Affinity;
            public uint PriorityClass;
            public uint SchedulingClass;
        }

        [System.Runtime.InteropServices.DllImport("kernel32.dll", SetLastError = true)]
        private static extern IntPtr CreateJobObjectW(IntPtr lpJobAttributes, string? lpName);

        [System.Runtime.InteropServices.DllImport("kernel32.dll", SetLastError = true)]
        private static extern bool SetInformationJobObject(IntPtr hJob, int infoClass, ref JOBOBJECT_BASIC_LIMIT_INFORMATION info, int cbSize);

        [System.Runtime.InteropServices.DllImport("kernel32.dll", SetLastError = true)]
        private static extern bool AssignProcessToJobObject(IntPtr hJob, IntPtr hProcess);

        public static void Assign(Process? proc)
        {
            if (proc == null) return;
            try
            {
                lock (_lock)
                {
                    if (_handle == IntPtr.Zero)
                    {
                        _handle = CreateJobObjectW(IntPtr.Zero, null);
                        if (_handle == IntPtr.Zero) return;
                        var info = new JOBOBJECT_BASIC_LIMIT_INFORMATION
                        {
                            LimitFlags = JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
                        };
                        if (!SetInformationJobObject(_handle, JobObjectBasicLimitInformation, ref info,
                            System.Runtime.InteropServices.Marshal.SizeOf<JOBOBJECT_BASIC_LIMIT_INFORMATION>()))
                        {
                            return;
                        }
                    }
                    AssignProcessToJobObject(_handle, proc.Handle);
                }
            }
            catch { /* без Job-объекта живём как раньше */ }
        }
    }
}
