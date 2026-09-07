// EkranchikAllInOne — трей-лаунчер полного режима (issue #3, ADR 0002).
//
// Сценарий: двойной клик → запуск backend (python -m uvicorn) → poll /health →
// запуск существующего Ekranchik.exe с URL дашборда → трей с «Открыть папку
// логов» / «Выход» (останавливает сервер и закрывает киоск).
//
// Конфигурирование под #5: JSON %LOCALAPPDATA%/Ekranchik/allinone_config.json
// + перекрывающие env-переменные EKRANCHIK_* (см. AllInOneConfig.FromEnvironment).
// В трее НЕТ портов/статусов — только действия.
//
// Тестовый крючок для smoke: флаг --auto-exit-after-ready=N (сек) — после
// успешного запуска киоска ждёт N сек и идёт по ТОМУ ЖЕ коду Shutdown(),
// что и пункт трея «Выход». Флаг не показывается пользователю.

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
            foreach (var arg in args)
            {
                const string prefix = "--auto-exit-after-ready=";
                if (arg.StartsWith(prefix, StringComparison.OrdinalIgnoreCase)
                    && int.TryParse(arg.Substring(prefix.Length), out int seconds)
                    && seconds > 0)
                {
                    autoExitAfterReady = seconds;
                }
            }

            var config = AllInOneConfig.Load();
            using (var context = new AllInOneContext(config, autoExitAfterReady))
            {
                Application.Run(context);
                return context.ExitCode;
            }
        }
    }

    // === Конфигурация (JSON + env-переопределения; расширяется в #5) ===
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

        private void ApplyEnvironmentOverrides()
        {
            string? Env(string name) => Environment.GetEnvironmentVariable(name);

            if (!string.IsNullOrWhiteSpace(Env("EKRANCHIK_PYTHON"))) PythonExe = Env("EKRANCHIK_PYTHON")!;
            if (!string.IsNullOrWhiteSpace(Env("EKRANCHIK_BACKEND_ARGS"))) BackendArgs = Env("EKRANCHIK_BACKEND_ARGS")!;
            if (!string.IsNullOrWhiteSpace(Env("EKRANCHIK_BACKEND_DIR"))) BackendDir = Env("EKRANCHIK_BACKEND_DIR")!;
            if (!string.IsNullOrWhiteSpace(Env("EKRANCHIK_KIOSK_EXE"))) KioskExe = Env("EKRANCHIK_KIOSK_EXE")!;
            if (!string.IsNullOrWhiteSpace(Env("EKRANCHIK_KIOSK_ARGS"))) KioskArgs = Env("EKRANCHIK_KIOSK_ARGS")!;
            if (!string.IsNullOrWhiteSpace(Env("EKRANCHIK_URL"))) DashboardUrl = Env("EKRANCHIK_URL")!;
            if (int.TryParse(Env("EKRANCHIK_PORT"), out int port) && port > 0 && port < 65536) Port = port;
            if (int.TryParse(Env("EKRANCHIK_READY_TIMEOUT_S"), out int timeout) && timeout > 0) ReadyTimeoutSeconds = timeout;
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

    // === Контекст приложения: backend → готовность → киоск → трей ===
    sealed class AllInOneContext : ApplicationContext
    {
        private readonly AllInOneConfig _config;
        private readonly int _autoExitAfterReady;
        private readonly RotatingLogger _appLog;
        private readonly RotatingLogger _backendLog;
        private readonly CancellationTokenSource _cts = new();

        private NotifyIcon? _tray;
        private Process? _backend;
        private Process? _kiosk;
        private bool _shutdownStarted;

        public int ExitCode { get; private set; }

        public AllInOneContext(AllInOneConfig config, int autoExitAfterReady)
        {
            _config = config;
            _autoExitAfterReady = autoExitAfterReady;
            _appLog = new RotatingLogger("allinone");
            _backendLog = new RotatingLogger("backend");
            _appLog.Write($"config: python={config.PythonExe} dir={config.BackendDir} " +
                $"args={config.ResolvedBackendArgs} url={config.ResolvedDashboardUrl} kiosk={config.KioskExe}");

            try
            {
                CreateTray();
            }
            catch (Exception ex)
            {
                // Без трея (headless) продолжаем: остановка — через Shutdown().
                _appLog.Write($"tray unavailable, continuing headless: {ex.Message}");
            }

            Task.Run(() => StartupSequenceAsync(_cts.Token));
        }

        // --- Трей: только действия, никаких портов/статусов ---
        private void CreateTray()
        {
            var menu = new ContextMenuStrip();
            menu.Items.Add(new ToolStripMenuItem("Открыть папку логов", null, (s, e) => OpenLogsFolder()));
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

        // Киоск читает URL из kiosk_config.json — подменяем только поле url,
        // остальные настройки (монитор, автозапуск, неизвестные ключи) сохраняем
        // как есть. Безопасность записи:
        //   - целый конфиг → копия в kiosk_config.json.bak до изменения;
        //   - битый конфиг → копия в kiosk_config.corrupt-<ts>.bak, затем
        //     минимальный валидный конфиг (настройки уже не спасти, но киоск
        //     стартует, а исходник лежит в бэкапе);
        //   - запись через tmp-файл + move (не бывает полузаписанного конфига).
        // Восстановление исходного URL — НЕ здесь (в проде URL должен остаться),
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
                string tmp = file + ".tmp";
                File.WriteAllText(tmp, JsonSerializer.Serialize(root,
                    new JsonSerializerOptions { WriteIndented = true }));
                File.Move(tmp, file, overwrite: true);
                _appLog.Write("kiosk_config.json url updated");
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
            try
            {
                MessageBox.Show(message + "\n\nПодробности — в папке логов Ekranchik.",
                    "Ekranchik", MessageBoxButtons.OK, MessageBoxIcon.Error);
            }
            catch { }
            Shutdown("fatal");
        }

        // --- Остановка: один путь и для трея «Выход», и для smoke-хука ---
        private void Shutdown(string reason)
        {
            if (_shutdownStarted) return;
            _shutdownStarted = true;
            _appLog.Write($"shutdown ({reason})");
            try { _cts.Cancel(); } catch { }

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

        protected override void Dispose(bool disposing)
        {
            if (disposing)
            {
                try { _cts.Dispose(); } catch { }
                try { _backend?.Dispose(); } catch { }
                try { _kiosk?.Dispose(); } catch { }
            }
            base.Dispose(disposing);
        }
    }
}
