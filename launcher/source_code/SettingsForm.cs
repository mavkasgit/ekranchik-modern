using System;
using System.Drawing;
using System.IO;
using System.Threading.Tasks;
using System.Windows.Forms;

namespace EkranchikShared
{
    // === Модель настроек для единого окна. Два приложения — два варианта
    // формы. Экран киоска: URL дашборда, монитор, автозапуск. Сервер:
    // серверная секция (Excel, OPC UA, симуляция, локалка) и «Адрес для
    // экранов» — то, что вводится в настройках экрана киоска. Секция,
    // которой у приложения нет, не показывается: null-свойство = «скрыть». ===
    public interface ISettingsModel
    {
        string? Url { get; }
        string? ExcelPath { get; }
        string? OpcuaEndpoint { get; }
        bool Simulation { get; }
        // Доступ с других машин локалки (--host 0.0.0.0). null-свойство =
        // «секцию не показывать» (киоск: у него своего сервера нет).
        bool? LanAccess { get; }
        // Выбор монитора — только экран киоска; у сервера null (секция скрыта).
        int? MonitorIndex { get; }
        // Порт дашборда для «Адреса для экранов»; у экрана null (секция скрыта).
        int? KioskPort { get; }
        bool WindowsAutostart { get; }
        bool AutoLaunchOnSecondMonitor { get; }

        void Save(string? url, string? excelPath, string? opcua, bool simulation,
                  bool lanAccess, int? monitorIndex, bool windowsAutostart,
                  bool autoLaunchOnSecondMonitor);
    }

    // === Обновления: общий контракт сервера и киоска (проверить /
    // установить в окне настроек). ===
    public interface IUpdateHost
    {
        string UpdateStatus { get; }
        bool HasPendingUpdate { get; }
        Task CheckForUpdatesAsync(bool manual);
        Task InstallUpdateAsync();
    }

    // === Хост единого окна настроек (только сервер): версии и действия
    // сервера. Экран киоска передаёт null — из окна убираются «Открыть
    // папку логов» и блок версий. ===
    public interface ISettingsHost : IUpdateHost
    {
        string VersionsText(string backendVersion);
        Task<string> GetBackendVersionAsync();
        void OpenLogsFolder();
        void OnSettingsSaved();
    }

    // Киоск-вариант модели: kiosk_config.json + автозапуск киоска в реестре
    // (логика KioskForm: галка применяется сразу).
    public sealed class KioskSettingsModel : ISettingsModel
    {
        private readonly KioskConfig _config;

        public KioskSettingsModel()
        {
            _config = ConfigManager.Load();
        }

        public string? Url => _config.url;
        public string? ExcelPath => null;
        public string? OpcuaEndpoint => null;
        public bool Simulation => false;
        public bool? LanAccess => null;
        public int? MonitorIndex => _config.monitor;
        // Адрес для экранов у экрана нечего показывать: он сам клиент.
        public int? KioskPort => null;
        public bool WindowsAutostart => _config.windows_startup;
        public bool AutoLaunchOnSecondMonitor => _config.auto_launch_on_second_monitor;

        public void Save(string? url, string? excelPath, string? opcua, bool simulation,
                         bool lanAccess, int? monitorIndex, bool windowsAutostart,
                         bool autoLaunchOnSecondMonitor)
        {
            ConfigManager.Save(url ?? _config.url, monitorIndex ?? _config.monitor,
                autoLaunchOnSecondMonitor, windowsAutostart);
            WindowsAutoStart.Apply(windowsAutostart, WindowsAutoStart.KioskValueName, WindowsAutoStart.KioskArgsSuffix);
        }
    }

    // === Единое окно настроек (issue #4/#9), стиль Slate-900/800, Segoe UI.
    // Киоск-вариант — сокращённый; серверный — с серверной секцией, версиями и
    // действиями сервера. ===
    public class SettingsForm : Form
    {
        private readonly ISettingsModel _model;
        private readonly ISettingsHost? _host;
        private readonly TextBox? _txtUrl;
        private readonly TextBox? _txtExcel;
        private readonly TextBox? _txtOpcua;
        private readonly CheckBox? _chkSim;
        private readonly CheckBox? _chkLan;
        private readonly ComboBox? _cmbMonitor;
        private readonly CheckBox _chkAutostart;
        private readonly CheckBox? _chkAutoLaunch;
        private readonly Label? _lblVersions;
        private readonly IUpdateHost? _updates;
        private readonly Label? _lblUpdateStatus;
        private readonly Button? _btnInstall;

        public SettingsForm(ISettingsModel model, ISettingsHost? host, IUpdateHost? updates = null)
        {
            _model = model;
            _host = host;
            // Обновления: хост сервера сам IUpdateHost; экран киоска передаёт
            // себя отдельным аргументом (host == null).
            _updates = updates ?? (IUpdateHost?)host;
            Color bgDark = Color.FromArgb(15, 23, 42);      // #0f172a
            Color bgCard = Color.FromArgb(30, 41, 59);      // #1e293b
            Color fgLight = Color.FromArgb(248, 250, 252);  // #f8fafc
            Color fgMuted = Color.FromArgb(148, 163, 184);  // slate-400
            Color accentBlue = Color.FromArgb(59, 130, 246); // #3b82f6
            Color borderGray = Color.FromArgb(51, 65, 85);   // #334155
            // Вёрстка окна задана в пикселях, рассчитанных для 96 dpi, поэтому
            // AutoScaleDimensions = 96 — точка отсчёта для AutoScaleMode.Dpi.
            // Без неё WinForms не знает, от чего масштабировать: окно остаётся
            // 540x800 физических пикселей, а текст рисуется в 150-250% dpi —
            // содержимое обрезается.
            this.AutoScaleDimensions = new SizeF(96F, 96F);
            this.AutoScaleMode = AutoScaleMode.Dpi;
            // Серверный вариант выше: серверная секция + адрес для экранов +
            // версии/обновления + действия. На низких разрешениях
            // ApplyDpiScale подрежет окно по рабочей области (AutoScroll).
            this.Size = host != null ? new Size(540, 840) : new Size(540, _updates != null ? 560 : 430);
            this.Text = "Ekranchik — Настройки";
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

            // --- URL (только киоск-вариант) ---
            if (model.Url != null)
            {
                var lblUrl = new Label
                {
                    Text = "URL дашборда:",
                    Font = new Font("Segoe UI", 9.5f, FontStyle.Bold),
                    Location = new Point(40, y),
                    Size = new Size(440, 20),
                    ForeColor = fgMuted
                };
                this.Controls.Add(lblUrl);
                y += 22;
                _txtUrl = new TextBox
                {
                    Text = model.Url,
                    Font = new Font("Segoe UI", 10),
                    BackColor = bgCard,
                    ForeColor = fgLight,
                    Location = new Point(40, y),
                    Size = new Size(440, 28),
                    BorderStyle = BorderStyle.FixedSingle
                };
                this.Controls.Add(_txtUrl);
                y += 44;
            }

            // --- Серверная секция (только у сервера) ---
            if (model.ExcelPath != null)
            {
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
                    Text = model.ExcelPath,
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
                    Text = model.OpcuaEndpoint,
                    Font = new Font("Segoe UI", 10),
                    BackColor = bgCard,
                    ForeColor = fgLight,
                    Location = new Point(40, y),
                    Size = new Size(440, 28),
                    BorderStyle = BorderStyle.FixedSingle
                };
                this.Controls.Add(_txtOpcua);
                y += 44;

                var chkSim = new CheckBox
                {
                    Text = "Тестовые данные (SIMULATION_ENABLED)",
                    Checked = model.Simulation,
                    Font = new Font("Segoe UI", 10),
                    Location = new Point(40, y),
                    Size = new Size(440, 26),
                    ForeColor = fgLight
                };
                _chkSim = chkSim;
                this.Controls.Add(chkSim);
                y += 34;

                _chkLan = new CheckBox
                {
                    Text = "Доступ из локальной сети (дашборд открывается с других ПК)",
                    Checked = model.LanAccess ?? false,
                    Font = new Font("Segoe UI", 10),
                    Location = new Point(40, y),
                    Size = new Size(440, 26),
                    ForeColor = fgLight
                };
                this.Controls.Add(_chkLan);
                y += 44;
            }

            // --- Монитор для киоска: только у экрана киоска. У сервера своих
            // мониторов нет, модель отдаёт null — секция не строится. ---
            ComboBox? cmbMonitor = null;
            if (model.MonitorIndex != null)
            {
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
                cmbMonitor = new ComboBox
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
                    cmbMonitor.Items.Add($"Монитор {i} — {name} ({s.Bounds.Width}x{s.Bounds.Height})");
                }
                if (cmbMonitor.Items.Count == 0)
                    cmbMonitor.Items.Add("Монитор 0");
                cmbMonitor.SelectedIndex = Math.Min(Math.Max(model.MonitorIndex.Value, 0), cmbMonitor.Items.Count - 1);
                this.Controls.Add(cmbMonitor);
                y += 44;
            }
            _cmbMonitor = cmbMonitor;

            // --- Адрес для экранов: только сервер. Это то, что оператор
            // вводит в поле «URL дашборда» настроек экрана киоска; сам адрес
            // собирает общий код по порту из конфига сервера. ---
            if (model.KioskPort != null)
            {
                var lblKioskAddr = new Label
                {
                    Text = "Адрес для экранов (вписать в настройки экрана киоска):",
                    Font = new Font("Segoe UI", 9.5f, FontStyle.Bold),
                    Location = new Point(40, y),
                    Size = new Size(440, 20),
                    ForeColor = fgMuted
                };
                this.Controls.Add(lblKioskAddr);
                y += 22;
                this.Controls.Add(new TextBox
                {
                    Text = KioskAddress.ForPort(model.KioskPort.Value),
                    ReadOnly = true,
                    Font = new Font("Segoe UI", 10),
                    BackColor = bgCard,
                    ForeColor = fgLight,
                    Location = new Point(40, y),
                    Size = new Size(440, 28),
                    BorderStyle = BorderStyle.FixedSingle
                });
                y += 30;
                var hintAddr = new Label
                {
                    Text = "Скопируйте адрес: с него экран киоска открывает дашборд.",
                    Font = new Font("Segoe UI", 8.5f),
                    Location = new Point(40, y),
                    Size = new Size(440, 20),
                    ForeColor = fgMuted
                };
                this.Controls.Add(hintAddr);
                y += 30;
            }

            // --- Автозапуск ---
            _chkAutostart = new CheckBox
            {
                Text = host != null
                    ? "Автозапуск Windows (старт в трей без окна)"
                    : "Автозапуск Windows",
                Checked = model.WindowsAutostart,
                Font = new Font("Segoe UI", 10),
                Location = new Point(40, y),
                Size = new Size(440, 26),
                ForeColor = fgLight
            };
            this.Controls.Add(_chkAutostart);
            y += 34;

            if (model.Url != null)
            {
                // Киоск-вариант: автозапуск на втором мониторе без окна настроек
                // (логика KioskForm).
                var chkAutoLaunch = new CheckBox
                {
                    Text = "Автозапуск на втором мониторе (без окна настроек)",
                    Checked = model.AutoLaunchOnSecondMonitor,
                    Font = new Font("Segoe UI", 10),
                    Location = new Point(40, y),
                    Size = new Size(440, 26),
                    ForeColor = fgLight
                };
                _chkAutoLaunch = chkAutoLaunch;
                this.Controls.Add(chkAutoLaunch);
                y += 34;
            }

            var hint = new Label
            {
                Text = host != null
                    ? "Excel, OPC UA и симуляция применяются при следующем запуске (env сервера). " +
                      "Автозапуск записывается в реестр сразу."
                    : "URL и монитор применяются сразу. Автозапуск записывается в реестр сразу.",
                Font = new Font("Segoe UI", 8.5f),
                Location = new Point(40, y),
                Size = new Size(440, 44),
                ForeColor = fgMuted
            };
            this.Controls.Add(hint);
            y += 52;

            // --- Версии, обновления и действия сервера. Секция обновлений
            // общая (появилась и в киоске — раньше была только в трее); версии
            // и действия — только у сервера. ---
            if (_updates != null)
            {
                var lblVerTitle = new Label
                {
                    Text = host != null ? "ВЕРСИИ И ОБНОВЛЕНИЯ" : "ОБНОВЛЕНИЕ",
                    Font = new Font("Segoe UI", 9.5f, FontStyle.Bold),
                    Location = new Point(20, y),
                    Size = new Size(480, 22),
                    TextAlign = ContentAlignment.MiddleCenter,
                    ForeColor = fgMuted
                };
                this.Controls.Add(lblVerTitle);
                y += 26;

                if (host != null)
                {
                    var lblVersions = new Label
                    {
                        Text = host.VersionsText("…"),
                        Font = new Font("Segoe UI", 9),
                        Location = new Point(40, y),
                        Size = new Size(440, 50),
                        ForeColor = fgLight
                    };
                    _lblVersions = lblVersions;
                    this.Controls.Add(lblVersions);
                    y += 54;
                }

                var lblUpdateStatus = new Label
                {
                    Text = _updates.UpdateStatus,
                    Font = new Font("Segoe UI", 9),
                    Location = new Point(40, y),
                    Size = new Size(440, 22),
                    ForeColor = fgMuted
                };
                _lblUpdateStatus = lblUpdateStatus;
                this.Controls.Add(lblUpdateStatus);
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
                    try { await _updates.CheckForUpdatesAsync(manual: true).ConfigureAwait(true); }
                    finally { btnCheck.Enabled = true; }
                    RefreshUpdateLabels();
                    RefreshBackendVersionAsync();
                };
                this.Controls.Add(btnCheck);

                var btnInstall = new Button
                {
                    Text = "Установить",
                    Font = new Font("Segoe UI", 9, FontStyle.Bold),
                    BackColor = accentBlue,
                    ForeColor = fgLight,
                    FlatStyle = FlatStyle.Flat,
                    Location = new Point(260, y),
                    Size = new Size(220, 32),
                    Cursor = Cursors.Hand,
                    Enabled = _updates.HasPendingUpdate
                };
                btnInstall.FlatAppearance.BorderSize = 0;
                btnInstall.Click += async (s, e) =>
                {
                    btnInstall.Enabled = false;
                    await _updates.InstallUpdateAsync().ConfigureAwait(true);
                    RefreshUpdateLabels();
                };
                _btnInstall = btnInstall;
                this.Controls.Add(btnInstall);
                y += 42;

                if (host != null)
                {
                    // «Показать экран» убрано: экран — отдельное приложение,
                    // показывать его серверу нечем.

                    var btnLogs = new Button
                    {
                        Text = "Открыть папку логов",
                        Font = new Font("Segoe UI", 9),
                        BackColor = bgCard,
                        ForeColor = fgLight,
                        FlatStyle = FlatStyle.Flat,
                        Location = new Point(40, y),
                        Size = new Size(440, 32),
                        Cursor = Cursors.Hand
                    };
                    btnLogs.FlatAppearance.BorderColor = borderGray;
                    btnLogs.Click += (s, e) => host.OpenLogsFolder();
                    this.Controls.Add(btnLogs);
                    y += 42;
                }

                RefreshBackendVersionAsync();
            }

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

            // Геометрия посчитана под 96 dpi — масштабируем под монитор.
            this.AutoScroll = true;
            ApplyDpiScale();
        }

        // Один вызов в конце конструктора: пересчитывает координаты всех
        // контролов и размер окна под текущий dpi монитора (мониторы линии
        // — 150-250% масштаба). Шрифты WinForms рисует сам по dpi, поэтому
        // масштабировать нужно только геометрию.
        private void ApplyDpiScale()
        {
            float k = DeviceDpi / 96f;
            if (k > 1.01f) Scale(new SizeF(k, k));
            // Экран ниже 200% на 1080p: окно не влезает — режем по рабочей
            // области, остальное доступно прокруткой (AutoScroll включён).
            Rectangle work = Screen.FromControl(this).WorkingArea;
            int maxH = work.Height - 40;
            if (Height > maxH) this.Size = new Size(Width, maxH);
        }

        private void BrowseExcel()
        {
            if (_txtExcel == null) return;
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
            try
            {
                _model.Save(
                    _txtUrl?.Text,
                    _txtExcel?.Text.Trim(),
                    _txtOpcua?.Text.Trim(),
                    _chkSim?.Checked ?? false,
                    _chkLan?.Checked ?? false,
                    _cmbMonitor != null ? Math.Max(_cmbMonitor.SelectedIndex, 0) : (int?)null,
                    _chkAutostart.Checked,
                    _chkAutoLaunch?.Checked ?? false);
            }
            catch (Exception ex)
            {
                MessageBox.Show(this, "Не удалось сохранить настройки:\n" + ex.Message,
                    "Ekranchik", MessageBoxButtons.OK, MessageBoxIcon.Error);
                return;
            }
            // Сервер применяет свои настройки (env, конфиг), экран киоска —
            // свой конфиг; перезапуск окна настроек тут ни при чём.
            _host?.OnSettingsSaved();
            this.DialogResult = DialogResult.OK;
            this.Close();
        }

        // Вызывает хост, когда фоновая проверка завершилась при открытом окне.
        public void RefreshFromUpdater()
        {
            if (_updates == null) return;
            RefreshUpdateLabels();
            RefreshBackendVersionAsync();
        }

        private void RefreshUpdateLabels()
        {
            if (_updates == null || _lblUpdateStatus == null || _btnInstall == null) return;
            _lblUpdateStatus.Text = _updates.UpdateStatus;
            _btnInstall.Enabled = _updates.HasPendingUpdate;
        }


        private async void RefreshBackendVersionAsync()
        {
            if (_host == null || _lblVersions == null) return;
            try
            {
                string backend = await _host.GetBackendVersionAsync().ConfigureAwait(true);
                if (this.IsDisposed)
                    return;
                _lblVersions.Text = _host.VersionsText(backend);
            }
            catch { }
        }
    }
}
