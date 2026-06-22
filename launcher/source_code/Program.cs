using System;
using System.IO;
using System.Net.Http;
using System.Threading;
using System.Threading.Tasks;
using System.Windows.Forms;
using System.Drawing;
using System.Text.Json;
using Microsoft.Web.WebView2.WinForms;
using Microsoft.Web.WebView2.Core;
using Microsoft.Win32;
using System.ComponentModel;

namespace EkranchikKiosk
{
    static class Program
    {
        [STAThread]
        static void Main(string[] args)
        {
            Application.EnableVisualStyles();
            Application.SetCompatibleTextRenderingDefault(false);

            bool noGui = false;
            foreach (var arg in args)
            {
                if (arg.Equals("--no-gui", StringComparison.OrdinalIgnoreCase))
                {
                    noGui = true;
                }
            }

            // Читаем конфигурацию
            var config = ConfigManager.Load();
            string configUrl = config.url;
            int configMonitor = config.monitor;

            // Если включен автозапуск на втором мониторе и экранов больше или равно 2, то обходим лаунчер
            bool bypassLauncher = noGui || (config.auto_launch_on_second_monitor && Screen.AllScreens.Length >= 2);

            if (!bypassLauncher)
            {
                using (var launcher = new LauncherForm(configUrl, configMonitor, config.auto_launch_on_second_monitor, config.windows_startup))
                {
                    if (launcher.ShowDialog() == DialogResult.OK)
                    {
                        configUrl = launcher.SelectedUrl;
                        configMonitor = launcher.SelectedMonitor;

                        // Сохраняем новые настройки в JSON и системный реестр Windows
                        ConfigManager.Save(configUrl, configMonitor, launcher.AutoLaunchOnSecond, launcher.WindowsStartup);
                    }
                    else
                    {
                        return; // Пользователь нажал Отмена
                    }
                }
            }

            // Запускаем основной Киоск
            Application.Run(new KioskForm(configUrl, configMonitor));
        }
    }

    // === Управление конфигурацией ===
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

                // Записываем автозапуск в реестр Windows
                SetWindowsAutostart(windowsStartup);
            }
            catch (Exception e)
            {
                Console.WriteLine($"[ERROR] Ошибка сохранения конфига: {e.Message}");
            }
        }

        private static void SetWindowsAutostart(bool enable)
        {
            try
            {
                using (RegistryKey key = Registry.CurrentUser.OpenSubKey(@"Software\Microsoft\Windows\CurrentVersion\Run", true))
                {
                    if (key != null)
                    {
                        if (enable)
                        {
                            key.SetValue("Ekranchik", $"\"{Application.ExecutablePath}\" --no-gui");
                        }
                        else
                        {
                            key.DeleteValue("Ekranchik", false);
                        }
                    }
                }
            }
            catch (Exception ex)
            {
                Console.WriteLine($"[ERROR] Ошибка изменения реестра автозапуска: {ex.Message}");
            }
        }
    }

    // === Круглый индикатор доступности ссылки ===
    public class StatusIndicator : Control
    {
        private Color indicatorColor = Color.Gray;
        
        [DesignerSerializationVisibility(DesignerSerializationVisibility.Hidden)]
        public Color IndicatorColor
        {
            get => indicatorColor;
            set
            {
                indicatorColor = value;
                if (this.InvokeRequired)
                {
                    try { this.BeginInvoke(new Action(() => this.Invalidate())); } catch { }
                }
                else
                {
                    this.Invalidate();
                }
            }
        }

        public StatusIndicator()
        {
            this.Size = new Size(16, 16);
            this.DoubleBuffered = true;
        }

        protected override void OnPaint(PaintEventArgs e)
        {
            base.OnPaint(e);
            e.Graphics.SmoothingMode = System.Drawing.Drawing2D.SmoothingMode.AntiAlias;
            using (var brush = new SolidBrush(indicatorColor))
            {
                e.Graphics.FillEllipse(brush, 1, 1, this.Width - 3, this.Height - 3);
            }
            using (var pen = new Pen(Color.FromArgb(51, 65, 85), 1.5f))
            {
                e.Graphics.DrawEllipse(pen, 1, 1, this.Width - 3, this.Height - 3);
            }
        }
    }

    // === Форма предзапуска / Выбора ссылки (Launcher) ===
    public class LauncherForm : Form
    {
        public string SelectedUrl { get; private set; }
        public int SelectedMonitor { get; private set; }
        public bool AutoLaunchOnSecond { get; private set; }
        public bool WindowsStartup { get; private set; }

        private TextBox txtUrl;
        private CheckBox chkAutoLaunch;
        private CheckBox chkWindowsStartup;

        private System.Threading.Timer? debounceTimer;
        private StatusIndicator txtUrlIndicator;

        // Переменные для динамического перестроения мониторов
        private int defaultMonitor;
        private Color bgCard;
        private Color fgLight;
        private Color accentBlue;
        private Color borderGray;
        private int monitorStartY;

        // Динамически воссоздаваемые элементы
        private List<RadioButton> radMonitors = new List<RadioButton>();
        private Label? lblMon;
        private Button? btnOk;
        private Button? btnCancel;

        public LauncherForm(string defaultUrl, int defaultMonitor, bool defaultAutoLaunch, bool defaultWindowsStartup)
        {
            SelectedUrl = defaultUrl;
            SelectedMonitor = defaultMonitor;
            AutoLaunchOnSecond = defaultAutoLaunch;
            WindowsStartup = defaultWindowsStartup;

            this.defaultMonitor = defaultMonitor;

            // Цветовая гамма Slate (Slate-900 / Slate-800)
            Color bgDark = Color.FromArgb(15, 23, 42);     // #0f172a
            this.bgCard = Color.FromArgb(30, 41, 59);     // #1e293b
            this.fgLight = Color.FromArgb(248, 250, 252); // #f8fafc
            this.accentBlue = Color.FromArgb(59, 130, 246); // #3b82f6
            this.borderGray = Color.FromArgb(51, 65, 85);   // #334155

            this.Text = "Ekranchik Settings";
            this.Size = new Size(500, 520);
            this.BackColor = bgDark;
            this.ForeColor = fgLight;
            this.FormBorderStyle = FormBorderStyle.FixedDialog;
            this.MaximizeBox = false;
            this.MinimizeBox = false;
            this.StartPosition = FormStartPosition.CenterScreen;
            this.ShowInTaskbar = true;

            try
            {
                this.Icon = Icon.ExtractAssociatedIcon(Application.ExecutablePath);
            }
            catch { }

            // Заголовок
            Label lblTitle = new Label
            {
                Text = "ВЫБОР ССЫЛКИ ДЛЯ ДАШБОРДА",
                Font = new Font("Segoe UI", 12, FontStyle.Bold),
                Location = new Point(20, 15),
                Size = new Size(460, 25),
                TextAlign = ContentAlignment.MiddleCenter
            };
            this.Controls.Add(lblTitle);

            // Кнопки быстрого выбора (только 3 варианта)
            var quickUrls = new[]
            {
                new { Label = "http://172.17.10.12:8083", Url = "http://172.17.10.12:8083" },
                new { Label = "http://172.17.11.8:5173", Url = "http://172.17.11.8:5173" },
                new { Label = "http://localhost:5173", Url = "http://localhost:5173" }
            };

            int startY = 50;
            foreach (var item in quickUrls)
            {
                Button btn = new Button
                {
                    Text = item.Label,
                    Font = new Font("Segoe UI", 9.5f, FontStyle.Bold),
                    BackColor = bgCard,
                    ForeColor = fgLight,
                    FlatStyle = FlatStyle.Flat,
                    Location = new Point(40, startY),
                    Size = new Size(370, 36),
                    Cursor = Cursors.Hand
                };
                btn.FlatAppearance.BorderColor = borderGray;
                btn.FlatAppearance.BorderSize = 1;

                btn.Click += (s, e) => {
                    txtUrl.Text = item.Url;
                };

                this.Controls.Add(btn);

                // Создаем и позиционируем индикатор справа от кнопки
                StatusIndicator ind = new StatusIndicator
                {
                    Location = new Point(425, startY + 10),
                    Size = new Size(16, 16)
                };
                this.Controls.Add(ind);

                // Запускаем асинхронную фоновую проверку
                Task.Run(() => CheckUrlAvailability(item.Url, ind));

                startY += 42;
            }

            // Поле для ручного ввода ссылки
            Label lblUrl = new Label
            {
                Text = "Адрес подключения (URL):",
                Font = new Font("Segoe UI", 9.5f, FontStyle.Bold),
                Location = new Point(40, startY + 10),
                Size = new Size(400, 20),
                ForeColor = Color.FromArgb(148, 163, 184)
            };
            this.Controls.Add(lblUrl);

            txtUrl = new TextBox
            {
                Text = defaultUrl,
                Font = new Font("Segoe UI", 10.5f),
                BackColor = bgCard,
                ForeColor = fgLight,
                Location = new Point(40, startY + 32),
                Size = new Size(370, 28),
                BorderStyle = BorderStyle.FixedSingle
            };
            txtUrl.TextChanged += TxtUrl_TextChanged;
            this.Controls.Add(txtUrl);

            txtUrlIndicator = new StatusIndicator
            {
                Location = new Point(425, startY + 38),
                Size = new Size(16, 16)
            };
            this.Controls.Add(txtUrlIndicator);

            // Проверяем начальный URL
            if (!string.IsNullOrEmpty(defaultUrl))
            {
                Task.Run(() => CheckUrlAvailability(defaultUrl, txtUrlIndicator));
            }

            startY += 70;
            this.monitorStartY = startY;

            // Строим выбор монитора
            RebuildMonitorSection();
        }

        private void RebuildMonitorSection()
        {
            if (this.InvokeRequired)
            {
                try { this.BeginInvoke(new Action(RebuildMonitorSection)); } catch { }
                return;
            }

            // Удаляем старые элементы
            if (lblMon != null) this.Controls.Remove(lblMon);
            foreach (var rad in radMonitors) this.Controls.Remove(rad);
            radMonitors.Clear();
            if (chkAutoLaunch != null) this.Controls.Remove(chkAutoLaunch);
            if (chkWindowsStartup != null) this.Controls.Remove(chkWindowsStartup);
            if (btnOk != null) this.Controls.Remove(btnOk);
            if (btnCancel != null) this.Controls.Remove(btnCancel);

            int startY = monitorStartY;

            // Выбор монитора
            lblMon = new Label
            {
                Text = "Выбор экрана:",
                Font = new Font("Segoe UI", 9.5f, FontStyle.Bold),
                Location = new Point(40, startY + 12),
                Size = new Size(400, 25),
                TextAlign = ContentAlignment.MiddleLeft,
                ForeColor = Color.FromArgb(148, 163, 184)
            };
            this.Controls.Add(lblMon);

            var screens = Screen.AllScreens;
            int radY = startY + 40;
            for (int i = 0; i < screens.Length; i++)
            {
                var s = screens[i];
                string name = s.Primary ? "Основной" : "Дополнительный";
                
                bool isChecked = (i == defaultMonitor) || (defaultMonitor >= screens.Length && i == 0);

                RadioButton rad = new RadioButton
                {
                    Text = $"Экран {i + 1}: {s.Bounds.Width}x{s.Bounds.Height} ({name})",
                    Font = new Font("Segoe UI", 9.5f, FontStyle.Bold),
                    Location = new Point(40, radY),
                    Size = new Size(370, 36),
                    Tag = i,
                    Checked = isChecked,
                    Appearance = Appearance.Button,
                    FlatStyle = FlatStyle.Flat,
                    BackColor = isChecked ? accentBlue : bgCard,
                    ForeColor = fgLight,
                    TextAlign = ContentAlignment.MiddleCenter,
                    Cursor = Cursors.Hand
                };
                rad.FlatAppearance.BorderColor = borderGray;
                rad.FlatAppearance.BorderSize = 1;

                rad.CheckedChanged += (snd, ev) => {
                    var r = (RadioButton)snd;
                    if (r.Checked)
                    {
                        r.BackColor = accentBlue;
                        r.ForeColor = Color.White;
                    }
                    else
                    {
                        r.BackColor = bgCard;
                        r.ForeColor = fgLight;
                    }
                };

                this.Controls.Add(rad);
                radMonitors.Add(rad);
                radY += 42;
            }

            startY = radY + 10;

            // Чекбоксы настроек автозапуска
            chkAutoLaunch = new CheckBox
            {
                Text = "Автоматически запускать при наличии второго экрана",
                Font = new Font("Segoe UI", 9.5f),
                Location = new Point(40, startY + 10),
                Size = new Size(420, 25),
                Checked = AutoLaunchOnSecond,
                FlatStyle = FlatStyle.Flat
            };
            this.Controls.Add(chkAutoLaunch);

            chkWindowsStartup = new CheckBox
            {
                Text = "Запускать автоматически при старте Windows",
                Font = new Font("Segoe UI", 9.5f),
                Location = new Point(40, startY + 40),
                Size = new Size(420, 25),
                Checked = WindowsStartup,
                FlatStyle = FlatStyle.Flat
            };
            this.Controls.Add(chkWindowsStartup);

            // Кнопка ОК / Запуск
            btnOk = new Button
            {
                Text = "Применить",
                Font = new Font("Segoe UI", 9.5f, FontStyle.Bold),
                Location = new Point(130, startY + 80),
                Size = new Size(110, 32),
                BackColor = Color.FromArgb(22, 163, 74), // Зеленый
                ForeColor = Color.White,
                FlatStyle = FlatStyle.Flat
            };
            btnOk.FlatAppearance.BorderSize = 0;
            btnOk.Click += (s, e) => {
                SelectedUrl = txtUrl.Text;
                
                SelectedMonitor = 0;
                foreach (var rad in radMonitors)
                {
                    if (rad.Checked)
                    {
                        SelectedMonitor = (int)rad.Tag;
                        break;
                    }
                }

                AutoLaunchOnSecond = chkAutoLaunch.Checked;
                WindowsStartup = chkWindowsStartup.Checked;
                this.DialogResult = DialogResult.OK;
                this.Close();
            };
            this.Controls.Add(btnOk);

            // Кнопка Отмена
            btnCancel = new Button
            {
                Text = "Отмена",
                Font = new Font("Segoe UI", 9.5f),
                Location = new Point(260, startY + 80),
                Size = new Size(110, 32),
                BackColor = bgCard,
                ForeColor = fgLight,
                FlatStyle = FlatStyle.Flat
            };
            btnCancel.FlatAppearance.BorderColor = borderGray;
            btnCancel.Click += (s, e) => {
                this.DialogResult = DialogResult.Cancel;
                this.Close();
            };
            this.Controls.Add(btnCancel);

            this.Size = new Size(500, startY + 160);
        }

        protected override void WndProc(ref Message m)
        {
            base.WndProc(ref m);
            const int WM_DISPLAYCHANGE = 0x007E;
            if (m.Msg == WM_DISPLAYCHANGE)
            {
                RebuildMonitorSection();
            }
        }

        private async Task CheckUrlAvailability(string url, StatusIndicator indicator)
        {
            if (indicator == null || indicator.IsDisposed) return;
            
            try
            {
                this.Invoke(new Action(() => {
                    indicator.IndicatorColor = Color.FromArgb(234, 179, 8); // Желтый (проверка)
                }));
            }
            catch { }

            using (var client = new HttpClient())
            {
                client.Timeout = TimeSpan.FromSeconds(2);
                try
                {
                    var response = await client.GetAsync(url);
                    if (response.IsSuccessStatusCode)
                    {
                        try
                        {
                            this.Invoke(new Action(() => {
                                indicator.IndicatorColor = Color.FromArgb(34, 197, 94); // Зеленый (доступен)
                            }));
                        }
                        catch { }
                        return;
                    }
                }
                catch { }
                
                try
                {
                    this.Invoke(new Action(() => {
                        indicator.IndicatorColor = Color.FromArgb(239, 68, 68); // Красный (недоступен)
                    }));
                }
                catch { }
            }
        }

        private void TxtUrl_TextChanged(object sender, EventArgs e)
        {
            string url = txtUrl.Text;
            txtUrlIndicator.IndicatorColor = Color.Gray;

            debounceTimer?.Dispose();
            debounceTimer = new System.Threading.Timer(async _ =>
            {
                if (Uri.TryCreate(url, UriKind.Absolute, out var uriResult) 
                    && (uriResult.Scheme == Uri.UriSchemeHttp || uriResult.Scheme == Uri.UriSchemeHttps))
                {
                    await CheckUrlAvailability(url, txtUrlIndicator);
                }
                else
                {
                    try
                    {
                        this.Invoke(new Action(() => {
                            txtUrlIndicator.IndicatorColor = Color.FromArgb(239, 68, 68); // Невалидный URL
                        }));
                    }
                    catch { }
                }
            }, null, 600, Timeout.Infinite);
        }

        protected override void OnFormClosing(FormClosingEventArgs e)
        {
            debounceTimer?.Dispose();
            base.OnFormClosing(e);
        }
    }

    // === Основное окно Киоска (Kiosk Mode) ===
    public class KioskForm : Form
    {
        private WebView2 webView;
        private string targetUrl;
        private int monitorIndex;
        private bool isIdleMode = false;
        private NotifyIcon trayIcon;
        private ToolStripMenuItem idleMenuItem;

        public KioskForm(string url, int monitor)
        {
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
            InitializeTray();

            // Перехват клавиш на уровне формы
            this.KeyPreview = true;
            this.KeyDown += KioskForm_KeyDown;
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

            // Создаем изолированную папку кэша/профиля WebView2
            string userDataFolder = Path.Combine(
                Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData),
                "EkranchikKiosk", "WebView2Data"
            );

            try
            {
                var env = await CoreWebView2Environment.CreateAsync(null, userDataFolder);
                await webView.EnsureCoreWebView2Async(env);
            }
            catch (Exception ex) {
                MessageBox.Show($"Ошибка инициализации WebView2: {ex.Message}", "Ошибка", MessageBoxButtons.OK, MessageBoxIcon.Error);
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

        private void CoreWebView2_WebMessageReceived(object sender, CoreWebView2WebMessageReceivedEventArgs e)
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

        private void KioskForm_KeyDown(object sender, KeyEventArgs e)
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

        private void CloseApp()
        {
            if (trayIcon != null)
            {
                trayIcon.Visible = false;
                trayIcon.Dispose();
            }
            webView?.Dispose();
            Application.Exit();
            Environment.Exit(0);
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

        private void ShowSettings()
        {
            this.Invoke(new Action(() => {
                var config = ConfigManager.Load();
                using (var launcher = new LauncherForm(config.url, config.monitor, config.auto_launch_on_second_monitor, config.windows_startup))
                {
                    launcher.StartPosition = FormStartPosition.CenterScreen;
                    launcher.TopMost = true;

                    if (launcher.ShowDialog(this) == DialogResult.OK)
                    {
                        ConfigManager.Save(launcher.SelectedUrl, launcher.SelectedMonitor, launcher.AutoLaunchOnSecond, launcher.WindowsStartup);
                        
                        if (launcher.SelectedUrl != targetUrl)
                        {
                            ChangeUrl(launcher.SelectedUrl);
                        }
                        
                        if (launcher.SelectedMonitor != monitorIndex)
                        {
                            monitorIndex = launcher.SelectedMonitor;
                            var screens = Screen.AllScreens;
                            if (monitorIndex < screens.Length)
                            {
                                var target = screens[monitorIndex];
                                this.WindowState = FormWindowState.Normal;
                                this.Bounds = target.Bounds;
                                this.WindowState = FormWindowState.Maximized;
                            }
                        }
                    }
                }
            }));
        }

        private void SwitchMonitor()
        {
            var screens = Screen.AllScreens;
            if (screens.Length < 2) return;

            monitorIndex = (monitorIndex + 1) % screens.Length;
            var target = screens[monitorIndex];

            // На Windows для переноса maximized/borderless окна нужно временно вернуть его в Normal
            this.WindowState = FormWindowState.Normal;
            this.Bounds = target.Bounds;
            this.WindowState = FormWindowState.Maximized;

            // Сохраняем изменения монитора в конфиг
            var config = ConfigManager.Load();
            ConfigManager.Save(targetUrl, monitorIndex, config.auto_launch_on_second_monitor, config.windows_startup);
        }

        private void ToggleIdleScreen()
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
        }

        // Поиск файла HTML в окрестностях и загрузка, либо загрузка fallback строки
        private void LoadLocalPage(string fileName, string fallbackHtml)
        {
            string foundPath = null;
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



        // === Fallback HTML-страницы ===
        private string GetFallbackWaitingHtml()
        {
            return @"
            <html>
            <head>
                <meta charset='utf-8'>
                <style>
                    body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; background-color: #0f172a; color: #f8fafc; display: flex; flex-direction: column; align-items: center; justify-content: center; height: 100vh; margin: 0; }
                    h1 { color: #f59e0b; }
                    p { color: #94a3b8; }
                </style>
            </head>
            <body>
                <h1>Связь потеряна</h1>
                <p>Ожидание подключения к бэкенду дашборда...</p>
            </body>
            </html>";
        }

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