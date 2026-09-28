using System;
using System.Windows.Forms;
using EkranchikShared;

namespace EkranchikKiosk
{
    static class Program
    {
        [STAThread]
        static void Main(string[] args)
        {
            Application.SetHighDpiMode(HighDpiMode.PerMonitorV2);
            Application.EnableVisualStyles();
            Application.SetCompatibleTextRenderingDefault(false);

            // Флаг самопроверки + обычный разбор аргументов.
            bool noGui = false;
            foreach (var arg in args)
            {
                if (arg.Equals("--self-test", StringComparison.OrdinalIgnoreCase))
                {
                    // Постоянные кейсы shared-модуля: stdout (если есть консоль) +
                    // лог в tmp + exit code, без UI.
                    int failures = UpdateSelfTest.Run(out string logPath);
                    try
                    {
                        Console.WriteLine($"self-test: {(failures == 0 ? "ALL OK" : failures + " FAILURES")} log={logPath}");
                    }
                    catch { }
                    Environment.Exit(failures == 0 ? 0 : 1);
                    return;
                }
                if (arg.Equals("--no-gui", StringComparison.OrdinalIgnoreCase))
                {
                    noGui = true;
                }
            }

            // Читаем конфигурацию
            var config = ConfigManager.Load();
            string configUrl = config.url;
            int configMonitor = config.monitor;

            // Если включен автозапуск на втором мониторе и экранов больше или
            // равно 2, то обходим окно настроек
            bool bypassLauncher = noGui || (config.auto_launch_on_second_monitor && Screen.AllScreens.Length >= 2);

            if (!bypassLauncher)
            {
                // Единое окно настроек в киоск-варианте (issue #9) — вместо
                // LauncherForm: выбрал → OK (модель уже сохранила конфиг),
                // Отмена = выход.
                using (var settings = new SettingsForm(new KioskSettingsModel(), host: null))
                {
                    if (settings.ShowDialog() == DialogResult.OK)
                    {
                        var saved = ConfigManager.Load();
                        configUrl = saved.url;
                        configMonitor = saved.monitor;
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
}
