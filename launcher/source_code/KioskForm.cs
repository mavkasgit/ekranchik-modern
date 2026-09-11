using System;
using System.Drawing;
using System.IO;
using System.Linq;
using System.Text.Json;
using System.Windows.Forms;
using Microsoft.Web.WebView2.Core;
using Microsoft.Web.WebView2.WinForms;

namespace EkranchikShared
{
    // === Хост киоска: контракт встроенного режима (issue #9). ===
    // Standalone (host == null) — самостоятельный киоск: свой трей, проверка
    // обновлений с баннером, Esc = выход из процесса.
    // Hosted (All-in-One) — окно экрана живёт в процессе полного приложения:
    // своего трея нет, наружу на дашборде ничего не показывается, Esc и
    // «Свернуть» = спрятать окно в трей; сервер продолжает работу.
    public interface IKioskHost
    {
        // Пользователь попросил закрыть экран: хост решает (прячет в трей).
        void OnKioskCloseRequested();
        // Переключение режима простоя — для текста пункта трея хоста.
        void OnIdleModeChanged(bool idle);
    }

    // === Конфигурация киоска: %LOCALAPPDATA%\Ekranchik\kiosk_config.json ===
    public class KioskConfig
    {
        public string url { get; set; } = "http://localhost:5173";
        public int monitor { get; set; } = 0;
        public bool auto_launch_on_second_monitor { get; set; } = false;
        public bool windows_startup { get; set; } = false;
    }

    public static class ConfigManager
    {
        private static readonly string ConfigDir = Path.Combine(
            Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData),
            "Ekranchik"
        );
        private static readonly string ConfigFile = Path.Combine(ConfigDir, "kiosk_config.json");

        public static KioskConfig Load()
        {
            var config = new KioskConfig();
            if (File.Exists(ConfigFile))
            {
                try
                {
                    string json = File.ReadAllText(ConfigFile);
                    var loaded = JsonSerializer.Deserialize<KioskConfig>(json);
                    if (loaded != null)
                    {
                        config = loaded;
                    }
                }
                catch { /* Игнорируем ошибки чтения */ }
            }
            return config;
        }

        // Запись настроек киоска. Автозапуск здесь НЕ пишется: реестром
        // управляет окно настроек (WindowsAutoStart.Apply) — иначе встроенный
        // режим постоянно перезаписывал бы Run-значение, мигрированное
        // All-in-One (issue #9).
        public static void Save(string url, int monitor, bool autoLaunch, bool windowsStartup)
        {
            try
            {
                Directory.CreateDirectory(ConfigDir);
                var config = new KioskConfig
                {
                    url = url,
                    monitor = monitor,
                    auto_launch_on_second_monitor = autoLaunch,
                    windows_startup = windowsStartup
                };

                string json = JsonSerializer.Serialize(config, new JsonSerializerOptions { WriteIndented = true });
                File.WriteAllText(ConfigFile, json);
            }
            catch (Exception e)
            {
                Console.WriteLine($"[ERROR] Ошибка сохранения конфига: {e.Message}");
            }
        }
    }

    // === Автозапуск Windows: HKCU Software\Microsoft\Windows\CurrentVersion\Run.
    // Общий для обоих приложений; имена значений не пересекаются: киоск —
    // "Ekranchik" (--no-gui), All-in-One — "EkranchikAllInOne" (--silent).
    // runKeyPath != null — тестовый подключ (smoke round-trip, настоящий Run
    // не пачкать). ===
    public static class WindowsAutoStart
    {
        public const string RealRunKeyPath = @"Software\Microsoft\Windows\CurrentVersion\Run";
        public const string KioskValueName = "Ekranchik";
        public const string KioskArgsSuffix = " --no-gui";
        public const string AllInOneValueName = "EkranchikAllInOne";
        public const string AllInOneArgsSuffix = " --silent";

        public static string EffectiveKeyPath(string? runKeyPath) =>
            string.IsNullOrWhiteSpace(runKeyPath) ? RealRunKeyPath : runKeyPath!;

        public static void Apply(bool enable, string valueName, string argsSuffix, string? runKeyPath = null)
        {
            string keyPath = EffectiveKeyPath(runKeyPath);
            using (var key = Microsoft.Win32.Registry.CurrentUser.CreateSubKey(keyPath, true))
            {
                if (key == null)
                    throw new InvalidOperationException($"cannot open HKCU\\{keyPath}");
                if (enable)
                    key.SetValue(valueName, $"\"{Application.ExecutablePath}\"{argsSuffix}");
                else
                    key.DeleteValue(valueName, throwOnMissingValue: false);
            }
        }

        // Миграция: удалить чужое значение (например, киоск-запись со старой
        // схемы, когда полный режим автостартовал два процесса).
        public static void DeleteValue(string valueName, string? runKeyPath = null)
        {
            string keyPath = EffectiveKeyPath(runKeyPath);
            using (var key = Microsoft.Win32.Registry.CurrentUser.OpenSubKey(keyPath, writable: true))
            {
                key?.DeleteValue(valueName, throwOnMissingValue: false);
            }
        }
    }

    // === Киоск: полноэкранное WebView2-окно дашборда на выделенном мониторе.
    // Самостоятельный киоск — ещё и IUpdateHost: проверка/установка обновлений
    // теперь в окне настроек (пункт трея убран), баннер на дашборде остался. ===
    public class KioskForm : Form, IUpdateHost
    {
        private readonly IKioskHost? _host;
        private readonly bool _hosted;
        private WebView2 webView = null!;
        private string targetUrl;
        private int monitorIndex;
        private bool isIdleMode = false;
        private NotifyIcon? trayIcon;
        private ToolStripMenuItem? idleMenuItem;
        private Panel? _updateBanner;
        private System.Threading.Timer? _updateTimer;
        private UpdateInfo? _pendingUpdate;
        private string _updateStatus = "Нажмите «Проверить обновления».";

        public KioskForm(string url, int monitor, IKioskHost? host = null)
        {
            this._host = host;
            this._hosted = host != null;
            this.targetUrl = url;
            this.monitorIndex = monitor;

            this.Text = "Ekranchik";
            this.FormBorderStyle = FormBorderStyle.None;
            this.WindowState = FormWindowState.Maximized;
            this.TopMost = true;
            this.ShowInTaskbar = true;
            this.BackColor = Color.FromArgb(15, 23, 42); // slate-900

            // Попытка извлечь иконку из ресурсов EXE
            try
            {
                this.Icon = Icon.ExtractAssociatedIcon(Application.ExecutablePath);
            }
            catch { }

            PositionOnMonitor();
            InitializeWebView();
            if (!_hosted)
            {
                InitializeTray();
            }

            // Перехват клавиш на уровне формы
            this.KeyPreview = true;
            this.KeyDown += KioskForm_KeyDown;
            if (!_hosted)
            {
                StartUpdateChecks();
            }
        }

        private void PositionOnMonitor()
        {
            var screens = Screen.AllScreens;
            if (monitorIndex >= 0 && monitorIndex < screens.Length)
            {
                var screen = screens[monitorIndex];
                this.StartPosition = FormStartPosition.Manual;
                this.Bounds = screen.Bounds;
            }
        }

        private void InitializeTray()
        {
            var trayMenu = new ContextMenuStrip();

            // Системные действия
            trayMenu.Items.Add(new ToolStripMenuItem("Переключить монитор", null, (s, e) => SwitchMonitor()));

            idleMenuItem = new ToolStripMenuItem("🕐 Режим простоя", null, (s, e) => ToggleIdleScreen());
            trayMenu.Items.Add(idleMenuItem);

            trayMenu.Items.Add(new ToolStripSeparator());

            // Кнопка настроек
            trayMenu.Items.Add(new ToolStripMenuItem("⚙️ Настройки", null, (s, e) => ShowSettings()));

            trayMenu.Items.Add(new ToolStripMenuItem("Выход", null, (s, e) => CloseApp()));

            trayIcon = new NotifyIcon
            {
                Text = "Ekranchik Control",
                ContextMenuStrip = trayMenu,
                Visible = true
            };

            try
            {
                trayIcon.Icon = Icon.ExtractAssociatedIcon(Application.ExecutablePath);
            }
            catch
            {
                trayIcon.Icon = SystemIcons.Application;
            }
        }

        private async void InitializeWebView()
        {
            webView = new WebView2 { Dock = DockStyle.Fill };
            this.Controls.Add(webView);

            // Создаем изолированную папку кэша/профиля WebView2. Встроенный
            // режим (issue #9) живёт в Ekranchik\ — не делит профиль с
            // самостоятельным киоском (они могут работать одновременно на
            // одной машине, например дев-киоск + merged).
            string profileRoot = _hosted ? "Ekranchik" : "EkranchikKiosk";
            string userDataFolder = Path.Combine(
                Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData),
                profileRoot, "WebView2Data"
            );

            try
            {
                var env = await CoreWebView2Environment.CreateAsync(null, userDataFolder);
                await webView.EnsureCoreWebView2Async(env);
            }
            catch (Exception ex)
            {
                MessageBox.Show($"Ошибка инициализации WebView2:\n\n{ex}", "Ошибка", MessageBoxButtons.OK, MessageBoxIcon.Error);
                if (_hosted)
                {
                    // Сервер продолжает работу — только прячем экран.
                    try { this.Hide(); } catch { }
                    _host?.OnKioskCloseRequested();
                    return;
                }
                Application.Exit();
                return;
            }

            // Настройки WebView2
            webView.CoreWebView2.Settings.AreDefaultContextMenusEnabled = false;
            webView.CoreWebView2.Settings.AreDevToolsEnabled = false;
            webView.CoreWebView2.Settings.IsZoomControlEnabled = false;

            // Обработка сообщений из JavaScript
            webView.CoreWebView2.WebMessageReceived += CoreWebView2_WebMessageReceived;

            // Инжектируем оригинальную панель управления с кнопками Свернуть "_" и Закрыть "×"
            string jsCode = GetInjectedJs();
            await webView.CoreWebView2.AddScriptToExecuteOnDocumentCreatedAsync(jsCode);

            // Дополнительная инжекция при завершении загрузки
            webView.NavigationCompleted += async (s, e) => {
                if (webView != null && webView.CoreWebView2 != null)
                {
                    try
                    {
                        await webView.CoreWebView2.ExecuteScriptAsync(jsCode);
                    }
                    catch { }
                }
            };

            // Сразу загружаем целевой URL бэкенда
            webView.CoreWebView2.Navigate(targetUrl);
        }

        private void CoreWebView2_WebMessageReceived(object? sender, CoreWebView2WebMessageReceivedEventArgs e)
        {
            try
            {
                string msg = e.TryGetWebMessageAsString();
                if (msg == "close_app")
                {
                    CloseApp();
                }
                else if (msg == "minimize_app")
                {
                    this.Invoke(new Action(() => {
                        if (_hosted)
                            Hide();
                        else
                            this.WindowState = FormWindowState.Minimized;
                    }));
                }
                else if (msg == "switch_monitor")
                {
                    this.Invoke(new Action(() => {
                        SwitchMonitor();
                    }));
                }
                else if (msg == "toggle_idle")
                {
                    this.Invoke(new Action(() => {
                        ToggleIdleScreen();
                    }));
                }
            }
            catch { }
        }

        private void KioskForm_KeyDown(object? sender, KeyEventArgs e)
        {
            if (e.KeyCode == Keys.F1)
            {
                SwitchMonitor();
                e.Handled = true;
            }
            else if (e.KeyCode == Keys.F2)
            {
                ToggleIdleScreen();
                e.Handled = true;
            }
            else if (e.KeyCode == Keys.Escape)
            {
                CloseApp();
                e.Handled = true;
            }
        }

        // Esc/крестик: standalone — выход из процесса; hosted — хост прячет
        // экран в трей (сервер работает, возврат кликом по иконке).
        private void CloseApp()
        {
            if (_hosted)
            {
                _host?.OnKioskCloseRequested();
                return;
            }
            try { _updateTimer?.Dispose(); } catch { }
            if (trayIcon != null)
            {
                trayIcon.Visible = false;
                trayIcon.Dispose();
            }
            webView?.Dispose();
            Application.Exit();
            Environment.Exit(0);
        }

        // Alt+F4/системное закрытие в встроенном режиме ведёт себя как Esc:
        // окно прячется, приложение продолжает работать.
        protected override void OnFormClosing(FormClosingEventArgs e)
        {
            base.OnFormClosing(e);
            if (_hosted && !e.Cancel)
            {
                e.Cancel = true;
                _host?.OnKioskCloseRequested();
            }
        }

        // === Проверка обновлений: канал v* + ассет Ekranchik.exe (тихий фейл без сети) ===
        // Только самостоятельный киоск; встроенный режим обновляется хостом.
        private void StartUpdateChecks()
        {
            Task.Run(() => CheckForUpdatesAsync(manual: false));
            _updateTimer = new System.Threading.Timer(
                _ => { Task.Run(() => CheckForUpdatesAsync(manual: false)); },
                null, UpdateChecker.Period, UpdateChecker.Period);
        }
        // Аргументы командной строки для рестарта после замены exe (уже квотированы).
        private static string RestartArgs
        {
            get
            {
                try
                {
                    var quoted = Environment.GetCommandLineArgs().Skip(1)
                        .Select(a => a.Contains(' ') || a.Contains('"') ? "\"" + a.Replace("\"", "\"\"") + "\"" : a);
                    string joined = string.Join(" ", quoted);
                    return joined.Length == 0 ? "" : " " + joined;
                }
                catch
                {
                    return "";
                }
            }
        }


        public string UpdateStatus => _updateStatus;
        public bool HasPendingUpdate => _pendingUpdate != null;

        public async Task CheckForUpdatesAsync(bool manual)
        {
            UpdateInfo? update = await UpdateChecker.CheckForUpdateAsync(
                AppVersion.Current, UpdateChecker.KioskChannelPrefix, "Ekranchik.exe").ConfigureAwait(false);
            if (update == null)
            {
                _pendingUpdate = null;
                _updateStatus = "У вас последняя версия.";
                return;
            }
            _pendingUpdate = update;
            _updateStatus = $"Доступна версия {update.Version} (текущая {AppVersion.Current}).";
            var pending = update;
            try { this.BeginInvoke(new Action(() => ShowUpdateBanner(pending))); } catch { }
        }

        // Установка из окна настроек: та же замена exe, что и из баннера.
        public async Task InstallUpdateAsync()
        {
            UpdateInfo? update = _pendingUpdate;
            if (update == null) return;
            _updateStatus = "Скачивание обновления...";
            try
            {
                await UpdateChecker.DownloadAndApplyKioskUpdateAsync(
                    update, Application.ExecutablePath, RestartArgs).ConfigureAwait(false);
            }
            catch (Exception ex)
            {
                _updateStatus = "Не удалось подготовить обновление (" + ex.Message + ").";
                try
                {
                    this.BeginInvoke(new Action(() => MessageBox.Show(
                        "Не удалось подготовить обновление (" + ex.Message + "). Проверьте сеть и попробуйте позже.",
                        "Ekranchik", MessageBoxButtons.OK, MessageBoxIcon.Warning)));
                }
                catch { }
            }
        }

        private void ShowUpdateBanner(UpdateInfo update)
        {
            if (_updateBanner != null)
                return;
            var banner = new Panel
            {
                Dock = DockStyle.Top,
                Height = 44,
                BackColor = Color.FromArgb(120, 53, 15)
            };
            var lbl = new Label
            {
                Text = $"Доступна версия {update.Version} (текущая {AppVersion.Current})",
                Dock = DockStyle.Fill,
                TextAlign = ContentAlignment.MiddleLeft,
                ForeColor = Color.White,
                Font = new Font("Segoe UI", 10, FontStyle.Bold),
                Padding = new Padding(12, 0, 0, 0)
            };
            banner.Controls.Add(lbl);
            var btn = new Button
            {
                Text = "Обновить",
                Dock = DockStyle.Right,
                Width = 130,
                BackColor = Color.FromArgb(59, 130, 246),
                ForeColor = Color.White,
                FlatStyle = FlatStyle.Flat,
                Font = new Font("Segoe UI", 10, FontStyle.Bold),
                Cursor = Cursors.Hand
            };
            btn.FlatAppearance.BorderSize = 0;
            btn.Click += async (s, e) =>
            {
                btn.Enabled = false;
                btn.Text = "Скачивание...";
                // Скачивание и подготовка замены — в фоне, дашборд не висит.
                string? updater = null;
                string? error = null;
                try
                {
                    updater = await UpdateChecker.DownloadAndApplyKioskUpdateAsync(
                        update, Application.ExecutablePath, RestartArgs).ConfigureAwait(false);
                }
                catch (Exception ex)
                {
                    error = ex.Message;
                }
                // На UI-поток — только UI-действия.
                try
                {
                    this.BeginInvoke(new Action(() =>
                    {
                        if (error != null && !this.IsDisposed)
                        {
                            btn.Enabled = true;
                            btn.Text = "Обновить";
                            MessageBox.Show(this, "Не удалось подготовить обновление (" + error + "). Проверьте сеть и попробуйте позже.",
                                "Ekranchik", MessageBoxButtons.OK, MessageBoxIcon.Warning);
                            return;
                        }
                        // Замена готова (или формы уже нет): updater ждёт выхода PID.
                        CloseApp();
                    }));
                }
                catch
                {
                    if (updater != null)
                    {
                        try { CloseApp(); } catch { }
                    }
                }
            };
            banner.Controls.Add(btn);
            var dismiss = new Button
            {
                Text = "✕",
                Dock = DockStyle.Right,
                Width = 44,
                BackColor = Color.FromArgb(120, 53, 15),
                ForeColor = Color.White,
                FlatStyle = FlatStyle.Flat,
                Cursor = Cursors.Hand
            };
            dismiss.FlatAppearance.BorderSize = 0;
            dismiss.Click += (s, e) =>
            {
                this.Controls.Remove(banner);
                banner.Dispose();
                if (ReferenceEquals(_updateBanner, banner))
                    _updateBanner = null;
            };
            banner.Controls.Add(dismiss);
            _updateBanner = banner;
            this.Controls.Add(banner);
            banner.BringToFront();
        }

        private void ChangeUrl(string newUrl)
        {
            targetUrl = newUrl;
            isIdleMode = false;
            if (idleMenuItem != null) idleMenuItem.Text = "🕐 Режим простоя";

            // Сохраняем в конфигурационный файл (с сохранением галочек)
            var config = ConfigManager.Load();
            ConfigManager.Save(newUrl, monitorIndex, config.auto_launch_on_second_monitor, config.windows_startup);

            this.Invoke(new Action(() => {
                webView.CoreWebView2.Navigate(targetUrl);
            }));
        }

        // Единое окно настроек в киоск-варианте (issue #9): URL, монитор,
        // автозапуск, обновления. Сохранённое применяется к живому экрану.
        private void ShowSettings()
        {
            this.Invoke(new Action(() => {
                using (var settings = new SettingsForm(new KioskSettingsModel(), host: null, updates: this))
                {
                    settings.StartPosition = FormStartPosition.CenterScreen;
                    settings.TopMost = true;

                    if (settings.ShowDialog(this) == DialogResult.OK)
                    {
                        var config = ConfigManager.Load(); // окно настроек уже сохранило
                        if (config.url != targetUrl)
                        {
                            ChangeUrl(config.url);
                        }
                        if (config.monitor != monitorIndex)
                        {
                            ApplyMonitor(config.monitor);
                        }
                    }
                }
            }));
        }

        // Циклический перенос окна на следующий монитор с записью в конфиг.
        public void SwitchMonitor()
        {
            var screens = Screen.AllScreens;
            if (screens.Length < 2) return;

            ApplyMonitor((monitorIndex + 1) % screens.Length);
        }

        // Позиционировать окно на конкретный монитор (Windows для переноса
        // maximized/borderless окна требует временный Normal) + конфиг.
        public void ApplyMonitor(int monitor)
        {
            var screens = Screen.AllScreens;
            this.monitorIndex = Math.Max(Math.Min(monitor, screens.Length - 1), 0);
            var target = screens[this.monitorIndex];

            this.WindowState = FormWindowState.Normal;
            this.Bounds = target.Bounds;
            this.WindowState = FormWindowState.Maximized;

            // Сохраняем изменения монитора в конфиг
            var config = ConfigManager.Load();
            ConfigManager.Save(targetUrl, this.monitorIndex, config.auto_launch_on_second_monitor, config.windows_startup);
        }

        public void ToggleIdleScreen()
        {
            if (isIdleMode)
            {
                isIdleMode = false;
                if (idleMenuItem != null) idleMenuItem.Text = "🕐 Режим простоя";
                webView.CoreWebView2.Navigate(targetUrl);
            }
            else
            {
                isIdleMode = true;
                if (idleMenuItem != null) idleMenuItem.Text = "💻 Вернуться к работе";
                LoadLocalPage("idle_clock.html", GetFallbackClockHtml());
            }
            _host?.OnIdleModeChanged(isIdleMode);
        }

        // Поиск файла HTML в окрестностях и загрузка, либо загрузка fallback строки
        private void LoadLocalPage(string fileName, string fallbackHtml)
        {
            string? foundPath = null;
            string baseDir = AppDomain.CurrentDomain.BaseDirectory;

            string[] searchPaths = new[]
            {
                Path.Combine(baseDir, fileName),
                Path.Combine(baseDir, "..", fileName),
                Path.Combine(baseDir, "..", "..", fileName),
                Path.Combine(baseDir, "..", "..", "..", fileName),
                Path.Combine(baseDir, "..", "..", "..", "..", fileName),
                Path.Combine(@"C:\Users\user\VibeCoding\ekranchik-modern\launcher", fileName)
            };

            foreach (var path in searchPaths)
            {
                if (File.Exists(path))
                {
                    foundPath = Path.GetFullPath(path);
                    break;
                }
            }

            if (foundPath != null && webView != null && webView.CoreWebView2 != null)
            {
                webView.CoreWebView2.Navigate(new Uri(foundPath).AbsoluteUri);
            }
            else if (webView != null && webView.CoreWebView2 != null)
            {
                webView.CoreWebView2.NavigateToString(fallbackHtml);
            }
        }

        // === Fallback HTML-страница часов простоя ===
        private string GetFallbackClockHtml()
        {
            return @"
            <html>
            <head>
                <meta charset='utf-8'>
                <style>
                    body { font-family: 'Segoe UI', Arial, sans-serif; background-color: #0f172a; color: #e0e7ff; display: flex; flex-direction: column; align-items: center; justify-content: center; height: 100vh; margin: 0; overflow: hidden; }
                    .time { font-size: 8rem; font-weight: bold; }
                    .date { font-size: 2rem; color: #64748b; margin-top: 10px; }
                    .mode-selector {
                        margin-top: 40px;
                        display: flex;
                        align-items: center;
                        gap: 15px;
                        background: rgba(30, 41, 59, 0.7);
                        padding: 10px 20px;
                        border-radius: 30px;
                        border: 1px solid rgba(255, 255, 255, 0.1);
                        box-shadow: 0 4px 20px rgba(0, 0, 0, 0.3);
                    }
                    .mode-label {
                        font-size: 1.1rem;
                        font-weight: 500;
                        color: #94a3b8;
                        min-width: 140px;
                        text-align: right;
                    }
                    .switch {
                        position: relative;
                        display: inline-block;
                        width: 60px;
                        height: 34px;
                    }
                    .switch input {
                        opacity: 0;
                        width: 0;
                        height: 0;
                    }
                    .slider {
                        position: absolute;
                        cursor: pointer;
                        top: 0; left: 0; right: 0; bottom: 0;
                        background-color: #475569;
                        transition: .4s;
                        border-radius: 34px;
                    }
                    .slider:before {
                        position: absolute;
                        content: '';
                        height: 26px;
                        width: 26px;
                        left: 4px;
                        bottom: 4px;
                        background-color: white;
                        transition: .4s;
                        border-radius: 50%;
                        box-shadow: 0 2px 5px rgba(0,0,0,0.3);
                    }
                    input:checked + .slider {
                        background-color: #3b82f6;
                    }
                    input:checked + .slider:before {
                        transform: translateX(26px);
                    }
                </style>
            </head>
            <body>
                <div class='time' id='clock'>00:00:00</div>
                <div class='date' id='date'>--.--.----</div>
                <div class='mode-selector'>
                    <span class='mode-label' id='mode-text'>Режим простоя</span>
                    <label class='switch'>
                        <input type='checkbox' id='mode-toggle' checked>
                        <span class='slider'></span>
                    </label>
                </div>
                <script>
                    function update() {
                        var now = new Date();
                        var pad = function(n) { return n < 10 ? '0' + n : n; };
                        document.getElementById('clock').textContent = pad(now.getHours()) + ':' + pad(now.getMinutes()) + ':' + pad(now.getSeconds());
                        document.getElementById('date').textContent = pad(now.getDate()) + '.' + pad(now.getMonth()+1) + '.' + now.getFullYear();
                    }
                    update();
                    setInterval(update, 1000);

                    var toggle = document.getElementById('mode-toggle');
                    var label = document.getElementById('mode-text');
                    toggle.addEventListener('change', function() {
                        if (!this.checked) {
                            label.textContent = 'Переход к работе...';
                            label.style.color = '#3b82f6';
                            setTimeout(function() {
                                if (window.chrome && window.chrome.webview) {
                                    window.chrome.webview.postMessage('toggle_idle');
                                }
                            }, 150);
                        } else {
                            label.textContent = 'Режим простоя';
                            label.style.color = '#94a3b8';
                        }
                    });
                </script>
            </body>
            </html>";
        }

        private string GetInjectedJs()
        {
            return @"
            (function() {
                var STYLE = [
                    'position:fixed',
                    'top:15px',
                    'right:15px',
                    'height:42px',
                    'border-radius:21px',
                    'background-color:rgba(15,23,42,0.75)',
                    'border:2px solid rgba(255,255,255,0.45)',
                    'display:flex',
                    'align-items:center',
                    'justify-content:center',
                    'padding:0 14px',
                    'gap:12px',
                    'z-index:2147483647',
                    'box-shadow:0 2px 16px rgba(0,0,0,0.7)',
                    'user-select:none',
                    'pointer-events:all'
                ].map(function(s){ return s+' !important'; }).join(';');

                var BTN_STYLE = [
                    'color:white',
                    'font-size:18px',
                    'cursor:pointer',
                    'display:flex',
                    'align-items:center',
                    'justify-content:center',
                    'width:28px',
                    'height:28px',
                    'border-radius:50%',
                    'transition:background-color 0.2s, transform 0.1s'
                ].map(function(s){ return s+' !important'; }).join(';');

                function inject() {
                    if (document.getElementById('ekranchik-ctrl-group')) return;

                    var target = document.body || document.documentElement;
                    if (!target) return;

                    var group = document.createElement('div');
                    group.id = 'ekranchik-ctrl-group';
                    group.setAttribute('style', STYLE);

                    var btnMon = document.createElement('div');
                    btnMon.innerHTML = '<svg xmlns=\'http://www.w3.org/2000/svg\' width=\'20\' height=\'20\' viewBox=\'0 0 24 24\' fill=\'none\' stroke=\'white\' stroke-width=\'3.5\' stroke-linecap=\'round\' stroke-linejoin=\'round\' style=\'pointer-events:none;display:block;\'><line x1=\'4\' y1=\'12\' x2=\'20\' y2=\'12\'></line><polyline points=\'12 4 20 12 12 20\'></polyline></svg>';
                    btnMon.title = 'Переключить монитор';
                    btnMon.setAttribute('style', BTN_STYLE + ';font-size:16px !important;');
                    btnMon.addEventListener('mouseenter', function() {
                        btnMon.style.setProperty('background-color','rgba(255,255,255,0.15)','important');
                    });
                    btnMon.addEventListener('mouseleave', function() {
                        btnMon.style.setProperty('background-color','transparent','important');
                    });
                    btnMon.addEventListener('click', function(e) {
                        e.stopPropagation();
                        e.preventDefault();
                        if (window.chrome && window.chrome.webview) {
                            window.chrome.webview.postMessage('switch_monitor');
                        }
                    });

                    var btnMin = document.createElement('div');
                    btnMin.innerHTML = '<svg xmlns=\'http://www.w3.org/2000/svg\' width=\'14\' height=\'14\' viewBox=\'0 0 24 24\' fill=\'none\' stroke=\'white\' stroke-width=\'3.5\' stroke-linecap=\'round\' stroke-linejoin=\'round\' style=\'pointer-events:none;display:block;\'><line x1=\'5\' y1=\'12\' x2=\'19\' y2=\'12\'></line></svg>';
                    btnMin.title = 'Свернуть';
                    btnMin.setAttribute('style', BTN_STYLE);
                    btnMin.addEventListener('mouseenter', function() {
                        btnMin.style.setProperty('background-color','rgba(255,255,255,0.15)','important');
                    });
                    btnMin.addEventListener('mouseleave', function() {
                        btnMin.style.setProperty('background-color','transparent','important');
                    });
                    btnMin.addEventListener('click', function(e) {
                        e.stopPropagation();
                        e.preventDefault();
                        if (window.chrome && window.chrome.webview) {
                            window.chrome.webview.postMessage('minimize_app');
                        }
                    });

                    var btnClose = document.createElement('div');
                    btnClose.innerHTML = '<svg xmlns=\'http://www.w3.org/2000/svg\' width=\'14\' height=\'14\' viewBox=\'0 0 24 24\' fill=\'none\' stroke=\'white\' stroke-width=\'3.5\' stroke-linecap=\'round\' stroke-linejoin=\'round\' style=\'pointer-events:none;display:block;\'><line x1=\'18\' y1=\'6\' x2=\'6\' y2=\'18\'></line><line x1=\'6\' y1=\'6\' x2=\'18\' y2=\'18\'></line></svg>';
                    btnClose.title = 'Выход';
                    btnClose.setAttribute('style', BTN_STYLE);
                    btnClose.addEventListener('mouseenter', function() {
                        btnClose.style.setProperty('background-color','rgba(220,38,38,0.95)','important');
                        btnClose.style.setProperty('transform','scale(1.1)','important');
                    });
                    btnClose.addEventListener('mouseleave', function() {
                        btnClose.style.setProperty('background-color','transparent','important');
                        btnClose.style.setProperty('transform','none','important');
                    });
                    btnClose.addEventListener('click', function(e) {
                        e.stopPropagation();
                        e.preventDefault();
                        if (window.chrome && window.chrome.webview) {
                            window.chrome.webview.postMessage('close_app');
                        }
                    });

                    group.appendChild(btnMon);
                    group.appendChild(btnMin);
                    group.appendChild(btnClose);
                    target.appendChild(group);
                }

                inject();
                new MutationObserver(function() {
                    if (!document.getElementById('ekranchik-ctrl-group')) inject();
                }).observe(document.documentElement, {childList:true, subtree:false});
                setInterval(inject, 1000);
            })();";
        }
    }
}
