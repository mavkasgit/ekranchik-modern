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
                    AutoStartManager.Apply(enable, runKeyArg);
                    Console.WriteLine($"autostart {(enable ? "enabled" : "disabled")} key={AutoStartManager.EffectiveKeyPath(runKeyArg)}");
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
            if (!string.IsNullOrWhiteSpace(Env("EKRANCHIK_KIOSK_EXE"))) KioskExe = Env("EKRANCHIK_KIOSK_EXE")!;
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
    // === Автозапуск Windows: HKCU Software\Microsoft\Windows\CurrentVersion\Run.
    // Имя значения — EkranchikAllInOne (не пересекается с "Ekranchik" киоска).
    // Команда — "<exe>" --silent: старт в трей без окна, стек поднимается сам.
    // Снятие галки удаляет запись. runKeyPath != null — тестовый подключ HKCU
    // (smoke round-trip, настоящий Run не пачкать).
    static class AutoStartManager
    {
        public const string ValueName = "EkranchikAllInOne";
        public const string RealRunKeyPath = @"Software\Microsoft\Windows\CurrentVersion\Run";

        public static string EffectiveKeyPath(string? runKeyPath) =>
            string.IsNullOrWhiteSpace(runKeyPath) ? RealRunKeyPath : runKeyPath!;

        public static void Apply(bool enable, string? runKeyPath = null)
        {
            string keyPath = EffectiveKeyPath(runKeyPath);
            using (RegistryKey key = Registry.CurrentUser.CreateSubKey(keyPath, true))
            {
                if (key == null)
                    throw new InvalidOperationException($"cannot open HKCU\\{keyPath}");
                if (enable)
                    key.SetValue(ValueName, $"\"{Application.ExecutablePath}\" --silent");
                else
                    key.DeleteValue(ValueName, throwOnMissingValue: false);
            }
        }

        public static bool IsEnabled(string? runKeyPath = null)
        {
            string keyPath = EffectiveKeyPath(runKeyPath);
            using (RegistryKey? key = Registry.CurrentUser.OpenSubKey(keyPath, writable: false))
            {
                return key?.GetValue(ValueName) != null;
            }
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

    // === Окно настроек (issue #4), в стиле киоска: Slate-900/800, Segoe UI. ===
    // Пять настроек persist-ятся в allinone_config.json: путь Excel, адрес
    // OPC UA, тестовые данные, монитор киоска, автозапуск Windows.
    sealed class SettingsForm : Form
    {
        private readonly AllInOneConfig _config;
        private readonly AllInOneContext _updater;
        private readonly TextBox _txtExcel;
        private readonly TextBox _txtOpcua;
        private readonly CheckBox _chkSim;
        private readonly ComboBox _cmbMonitor;
        private readonly CheckBox _chkAutostart;
        private readonly Label _lblVersions;
        private readonly Label _lblUpdateStatus;
        private readonly Button _btnInstall;

        public SettingsForm(AllInOneConfig config, AllInOneContext updater)
        {
            _config = config;
            _updater = updater;

            Color bgDark = Color.FromArgb(15, 23, 42);      // #0f172a
            Color bgCard = Color.FromArgb(30, 41, 59);      // #1e293b
            Color fgLight = Color.FromArgb(248, 250, 252);  // #f8fafc
            Color fgMuted = Color.FromArgb(148, 163, 184);  // slate-400
            Color accentBlue = Color.FromArgb(59, 130, 246); // #3b82f6
            Color borderGray = Color.FromArgb(51, 65, 85);   // #334155

            this.Text = "Ekranchik — Настройки";
            this.Size = new Size(540, 710);
            this.BackColor = bgDark;
            this.ForeColor = fgLight;
            this.FormBorderStyle = FormBorderStyle.FixedDialog;
            this.MaximizeBox = false;
            this.MinimizeBox = false;
            this.StartPosition = FormStartPosition.CenterScreen;
            this.ShowInTaskbar = true;
            try { this.Icon = Icon.ExtractAssociatedIcon(Application.ExecutablePath); }
            catch { }

            var title = new Label
            {
                Text = "НАСТРОЙКИ EKRANCHIK",
                Font = new Font("Segoe UI", 12, FontStyle.Bold),
                Location = new Point(20, 15),
                Size = new Size(480, 25),
                TextAlign = ContentAlignment.MiddleCenter
            };
            this.Controls.Add(title);

            int y = 55;
            var lblExcel = new Label
            {
                Text = "Путь к Excel (сетевой):",
                Font = new Font("Segoe UI", 9.5f, FontStyle.Bold),
                Location = new Point(40, y),
                Size = new Size(440, 20),
                ForeColor = fgMuted
            };
            this.Controls.Add(lblExcel);
            y += 22;
            _txtExcel = new TextBox
            {
                Text = config.ExcelPath,
                Font = new Font("Segoe UI", 10),
                BackColor = bgCard,
                ForeColor = fgLight,
                Location = new Point(40, y),
                Size = new Size(350, 28),
                BorderStyle = BorderStyle.FixedSingle
            };
            this.Controls.Add(_txtExcel);
            var btnBrowse = new Button
            {
                Text = "Обзор...",
                Font = new Font("Segoe UI", 9.5f, FontStyle.Bold),
                BackColor = bgCard,
                ForeColor = fgLight,
                FlatStyle = FlatStyle.Flat,
                Location = new Point(400, y - 1),
                Size = new Size(80, 28),
                Cursor = Cursors.Hand
            };
            btnBrowse.FlatAppearance.BorderColor = borderGray;
            btnBrowse.Click += (s, e) => BrowseExcel();
            this.Controls.Add(btnBrowse);
            y += 40;

            var lblOpcua = new Label
            {
                Text = "Адрес OPC UA:",
                Font = new Font("Segoe UI", 9.5f, FontStyle.Bold),
                Location = new Point(40, y),
                Size = new Size(440, 20),
                ForeColor = fgMuted
            };
            this.Controls.Add(lblOpcua);
            y += 22;
            _txtOpcua = new TextBox
            {
                Text = config.OpcuaEndpoint,
                Font = new Font("Segoe UI", 10),
                BackColor = bgCard,
                ForeColor = fgLight,
                Location = new Point(40, y),
                Size = new Size(440, 28),
                BorderStyle = BorderStyle.FixedSingle
            };
            this.Controls.Add(_txtOpcua);
            y += 44;

            _chkSim = new CheckBox
            {
                Text = "Тестовые данные (SIMULATION_ENABLED)",
                Checked = config.SimulationEnabled,
                Font = new Font("Segoe UI", 10),
                Location = new Point(40, y),
                Size = new Size(440, 26),
                ForeColor = fgLight
            };
            this.Controls.Add(_chkSim);
            y += 34;

            var lblMonitor = new Label
            {
                Text = "Монитор для киоска:",
                Font = new Font("Segoe UI", 9.5f, FontStyle.Bold),
                Location = new Point(40, y),
                Size = new Size(440, 20),
                ForeColor = fgMuted
            };
            this.Controls.Add(lblMonitor);
            y += 22;
            _cmbMonitor = new ComboBox
            {
                DropDownStyle = ComboBoxStyle.DropDownList,
                Font = new Font("Segoe UI", 10),
                BackColor = bgCard,
                ForeColor = fgLight,
                Location = new Point(40, y),
                Size = new Size(440, 28)
            };
            var screens = Screen.AllScreens;
            for (int i = 0; i < screens.Length; i++)
            {
                var s = screens[i];
                string name = s.Primary ? "Основной" : "Дополнительный";
                _cmbMonitor.Items.Add($"Монитор {i} — {name} ({s.Bounds.Width}x{s.Bounds.Height})");
            }
            if (_cmbMonitor.Items.Count == 0)
                _cmbMonitor.Items.Add("Монитор 0");
            _cmbMonitor.SelectedIndex = Math.Min(Math.Max(config.KioskMonitor, 0), _cmbMonitor.Items.Count - 1);
            this.Controls.Add(_cmbMonitor);
            y += 44;

            _chkAutostart = new CheckBox
            {
                Text = "Автозапуск Windows (старт в трей без окна)",
                Checked = config.AutoStart,
                Font = new Font("Segoe UI", 10),
                Location = new Point(40, y),
                Size = new Size(440, 26),
                ForeColor = fgLight
            };
            this.Controls.Add(_chkAutostart);
            y += 36;

            var hint = new Label
            {
                Text = "Excel, OPC UA и симуляция применяются при следующем запуске (env сервера). " +
                    "Монитор — при запуске киоска. Автозапуск записывается в реестр сразу.",
                Font = new Font("Segoe UI", 8.5f),
                Location = new Point(40, y),
                Size = new Size(440, 44),
                ForeColor = fgMuted
            };
            this.Controls.Add(hint);
            y += 52;
            var lblVerTitle = new Label
            {
                Text = "ВЕРСИИ И ОБНОВЛЕНИЯ",
                Font = new Font("Segoe UI", 9.5f, FontStyle.Bold),
                Location = new Point(20, y),
                Size = new Size(480, 22),
                TextAlign = ContentAlignment.MiddleCenter,
                ForeColor = fgMuted
            };
            this.Controls.Add(lblVerTitle);
            y += 26;

            _lblVersions = new Label
            {
                Text = _updater.VersionsText("…"),
                Font = new Font("Segoe UI", 9),
                Location = new Point(40, y),
                Size = new Size(440, 50),
                ForeColor = fgLight
            };
            this.Controls.Add(_lblVersions);
            y += 54;

            _lblUpdateStatus = new Label
            {
                Text = _updater.UpdateStatus,
                Font = new Font("Segoe UI", 9),
                Location = new Point(40, y),
                Size = new Size(440, 22),
                ForeColor = fgMuted
            };
            this.Controls.Add(_lblUpdateStatus);
            y += 26;

            var btnCheck = new Button
            {
                Text = "Проверить обновления",
                Font = new Font("Segoe UI", 9),
                BackColor = bgCard,
                ForeColor = fgLight,
                FlatStyle = FlatStyle.Flat,
                Location = new Point(40, y),
                Size = new Size(210, 32),
                Cursor = Cursors.Hand
            };
            btnCheck.FlatAppearance.BorderColor = borderGray;
            btnCheck.Click += async (s, e) =>
            {
                btnCheck.Enabled = false;
                try { await _updater.CheckForUpdatesAsync(manual: true).ConfigureAwait(true); }
                finally { btnCheck.Enabled = true; }
                RefreshUpdateLabels();
                RefreshBackendVersionAsync();
            };
            this.Controls.Add(btnCheck);

            _btnInstall = new Button
            {
                Text = "Установить",
                Font = new Font("Segoe UI", 9, FontStyle.Bold),
                BackColor = accentBlue,
                ForeColor = fgLight,
                FlatStyle = FlatStyle.Flat,
                Location = new Point(260, y),
                Size = new Size(220, 32),
                Cursor = Cursors.Hand,
                Enabled = _updater.HasPendingUpdate
            };
            _btnInstall.FlatAppearance.BorderSize = 0;
            _btnInstall.Click += async (s, e) =>
            {
                _btnInstall.Enabled = false;
                await _updater.InstallUpdateAsync().ConfigureAwait(true);
                RefreshUpdateLabels();
            };
            this.Controls.Add(_btnInstall);
            y += 42;

            RefreshBackendVersionAsync();

            var btnSave = new Button
            {
                Text = "Сохранить",
                Font = new Font("Segoe UI", 10, FontStyle.Bold),
                BackColor = accentBlue,
                ForeColor = fgLight,
                FlatStyle = FlatStyle.Flat,
                Location = new Point(140, y),
                Size = new Size(140, 36),
                Cursor = Cursors.Hand,
                DialogResult = DialogResult.None
            };
            btnSave.FlatAppearance.BorderSize = 0;
            btnSave.Click += (s, e) => SaveAndClose();
            this.Controls.Add(btnSave);
            this.AcceptButton = btnSave;

            var btnCancel = new Button
            {
                Text = "Отмена",
                Font = new Font("Segoe UI", 10),
                BackColor = bgCard,
                ForeColor = fgLight,
                FlatStyle = FlatStyle.Flat,
                Location = new Point(300, y),
                Size = new Size(140, 36),
                Cursor = Cursors.Hand,
                DialogResult = DialogResult.Cancel
            };
            btnCancel.FlatAppearance.BorderColor = borderGray;
            this.Controls.Add(btnCancel);
            this.CancelButton = btnCancel;
        }

        private void BrowseExcel()
        {
            using (var dlg = new OpenFileDialog())
            {
                dlg.Title = "Путь к Excel-книге учёта";
                dlg.Filter = "Excel (*.xlsm;*.xlsx)|*.xlsm;*.xlsx|Все файлы (*.*)|*.*";
                try
                {
                    if (!string.IsNullOrWhiteSpace(_txtExcel.Text))
                    {
                        string dir = Path.GetDirectoryName(_txtExcel.Text) ?? "";
                        if (Directory.Exists(dir)) dlg.InitialDirectory = dir;
                        dlg.FileName = Path.GetFileName(_txtExcel.Text);
                    }
                }
                catch { }
                if (dlg.ShowDialog(this) == DialogResult.OK)
                    _txtExcel.Text = dlg.FileName;
            }
        }

        private void SaveAndClose()
        {
            _config.ExcelPath = _txtExcel.Text.Trim();
            _config.OpcuaEndpoint = _txtOpcua.Text.Trim();
            _config.SimulationEnabled = _chkSim.Checked;
            _config.KioskMonitor = Math.Max(_cmbMonitor.SelectedIndex, 0);
            _config.AutoStart = _chkAutostart.Checked;
            try
            {
                _config.Save();
            }
            catch (Exception ex)
            {
                MessageBox.Show(this, "Не удалось сохранить настройки:\n" + ex.Message,
                    "Ekranchik", MessageBoxButtons.OK, MessageBoxIcon.Error);
                return;
            }
            try
            {
                AutoStartManager.Apply(_config.AutoStart);
            }
            catch (Exception ex)
            {
                MessageBox.Show(this, "Настройки сохранены, но автозапуск не применён:\n" + ex.Message,
                    "Ekranchik", MessageBoxButtons.OK, MessageBoxIcon.Warning);
                return;
            }
            this.DialogResult = DialogResult.OK;
            this.Close();
        }

        // Вызывает контекст, когда фоновая проверка завершилась при открытом окне.
        public void RefreshFromUpdater()
        {
            RefreshUpdateLabels();
            RefreshBackendVersionAsync();
        }

        private void RefreshUpdateLabels()
        {
            _lblUpdateStatus.Text = _updater.UpdateStatus;
            _btnInstall.Enabled = _updater.HasPendingUpdate;
        }

        private async void RefreshBackendVersionAsync()
        {
            try
            {
                string backend = await _updater.GetBackendVersionAsync().ConfigureAwait(true);
                if (this.IsDisposed)
                    return;
                _lblVersions.Text = _updater.VersionsText(backend);
            }
            catch { }
        }
    }

    // === Контекст приложения: backend → готовность → киоск → трей ===
    sealed class AllInOneContext : ApplicationContext
    {
        private readonly AllInOneConfig _config;
        private readonly int _autoExitAfterReady;
        private readonly bool _silent;
        private readonly RotatingLogger _appLog;
        private readonly RotatingLogger _backendLog;
        private readonly CancellationTokenSource _cts = new();

        private NotifyIcon? _tray;
        private Process? _backend;
        private Process? _kiosk;
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
            _appLog.Write($"config: python={config.PythonExe} dir={config.BackendDir} " +
                $"args={config.ResolvedBackendArgs} url={config.ResolvedDashboardUrl} kiosk={config.KioskExe}");
            _appLog.Write($"settings: excel={config.ExcelPath} opcua={config.OpcuaEndpoint} " +
                $"sim={config.SimulationEnabled} monitor={config.KioskMonitor} autostart={config.AutoStart}");
            SyncAutoStart();

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
                AutoStartManager.Apply(_config.AutoStart);
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
                _settingsForm = new SettingsForm(_config, this);
                _settingsForm.FormClosed += (s, e) => { _settingsForm = null; };
                _settingsForm.Show();
            }
            catch (Exception ex)
            {
                _appLog.Write($"settings window failed: {ex.Message}");
            }
        }

        // --- Трей: только действия, никаких портов/статусов ---
        private void CreateTray()
        {
            var menu = new ContextMenuStrip();
            menu.Items.Add(new ToolStripMenuItem("Настройки...", null, (s, e) => ShowSettings()));
            menu.Items.Add(new ToolStripMenuItem("Открыть папку логов", null, (s, e) => OpenLogsFolder()));
            menu.Items.Add(new ToolStripMenuItem("Проверить обновления", null, (s, e) => { Task.Run(() => CheckForUpdatesAsync(manual: true)); }));
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
            _tray.BalloonTipClicked += (s, e) => { Task.Run(() => InstallUpdateAsync()); };
        }

        private void OpenLogsFolder()
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
            try
            {
                if (!File.Exists(_config.KioskExe))
                {
                    _appLog.Write($"kiosk exe not found, skipping: {_config.KioskExe}");
                    return; // Сервер уже работает — отсутствие киоска не фатально.
                }
                PointKioskConfigAtDashboard();
                // URL позиционным аргументом (киоск берёт URL из конфига, лишние
                // аргументы игнорирует) + --no-gui против окна настроек.
                var psi = new ProcessStartInfo
                {
                    FileName = _config.KioskExe,
                    Arguments = _config.ResolvedKioskArgs,
                    UseShellExecute = false
                };
                _kiosk = Process.Start(psi);
                _appLog.Write($"kiosk started pid={_kiosk?.Id}");
            }
            catch (Exception ex)
            {
                _appLog.Write($"kiosk start failed (backend keeps running): {ex.Message}");
            }
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
            return $"All-in-One: {AppVersion.Current}\nBackend: {backendVersion}\nКиоск: {KioskVersionText()}";
        }

        public string KioskVersionText()
        {
            try
            {
                string exe = _config.KioskExe;
                if (File.Exists(exe))
                {
                    string? v = FileVersionInfo.GetVersionInfo(exe).ProductVersion;
                    if (!string.IsNullOrWhiteSpace(v))
                        return v.Split('+')[0].Trim();
                }
            }
            catch { }
            return "—";
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
}
