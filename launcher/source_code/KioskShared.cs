// Общие для обоих приложений типы: конфигурация экрана киоска и автозапуск
// Windows. Лежат отдельным файлом, потому что нужны и киоску (Ekranchik.exe),
// и серверу (EkranchikServer.exe): сервер собирает то же окно настроек и тоже
// пишет своё значение в Run. Экран киоска при этом самостоятельный — встроенного
// режима больше нет.

using System;
using System.IO;
using System.Text.Json;
using System.Windows.Forms;

namespace EkranchikShared
{
    // === Конфигурация киоска: %LOCALAPPDATA%\Ekranchik\kiosk_config.json ===
    public class KioskConfig
    {
        // Адрес по умолчанию — тот же, что кладёт установщик закладкой
        // эталона: порт дашборда 8083 (CONTEXT.md, «Адрес для экранов»).
        // Dev-порт vite сюда попадать не должен: на машине экрана его не
        // поднимает никто, и экран без настроек открывал бы мёртвый адрес.
        // Разработчик указывает адрес своего дев-сервера явно — в поле
        // «URL дашборда» настроек экрана (пишется в этот же конфиг).
        public string url { get; set; } = "http://localhost:8083";
        public int monitor { get; set; } = 0;
        public bool auto_launch_on_second_monitor { get; set; } = false;
        public bool windows_startup { get; set; } = false;
    }

    // === Адрес, который оператор вводит в настройках экрана киоска:
    // «http://<ip этой машины в локалке>:<порт дашборда>». Само вычисление
    // живёт здесь, в общем коде, а модель настроек сервера только отдаёт
    // порт из своего конфига — дублировать подбор IP в приложениях не надо. ===
    public static class KioskAddress
    {
        public static string ForPort(int port) => $"http://{LanAddress()}:{port}";

        // Первый IPv4 не из петли на поднятом адаптере. Адреса виртуальных
        // адаптеров (VPN, Hyper-V) тоже подходят: с такого адреса дашборд
        // обычно и открывают, а выбор за оператором.
        public static string LanAddress()
        {
            try
            {
                foreach (var nic in System.Net.NetworkInformation.NetworkInterface
                    .GetAllNetworkInterfaces())
                {
                    if (nic.OperationalStatus !=
                            System.Net.NetworkInformation.OperationalStatus.Up) continue;
                    foreach (var ip in nic.GetIPProperties().UnicastAddresses)
                    {
                        if (ip.Address.AddressFamily == System.Net.Sockets.AddressFamily.InterNetwork
                            && !System.Net.IPAddress.IsLoopback(ip.Address))
                            return ip.Address.ToString();
                    }
                }
            }
            catch { }
            return "localhost";
        }
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
        // управляет окно настроек (WindowsAutoStart.Apply), чтобы каждый
        // экран и сервер синхронизировали своё значение в одном месте.
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
    // Имена значений не пересекаются: экран киоска — "Ekranchik" (--no-gui),
    // сервер — "EkranchikServer" (--silent). runKeyPath != null — тестовый
    // подключ (smoke round-trip, настоящий Run не пачкать). ===
    public static class WindowsAutoStart
    {
        public const string RealRunKeyPath = @"Software\Microsoft\Windows\CurrentVersion\Run";
        public const string KioskValueName = "Ekranchik";
        public const string KioskArgsSuffix = " --no-gui";
        public const string ServerValueName = "EkranchikServer";
        public const string ServerArgsSuffix = " --silent";
        // Значение прежней поставки (EkranchikAllInOne): больше не поставляется,
        // сервер удаляет его при старте.
        public const string LegacyAutostartValueName = "EkranchikAllInOne";

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

        // Миграция: удалить чужое значение (например, запись прежней поставки,
        // которого больше нет на диске).
        public static void DeleteValue(string valueName, string? runKeyPath = null)
        {
            string keyPath = EffectiveKeyPath(runKeyPath);
            using (var key = Microsoft.Win32.Registry.CurrentUser.OpenSubKey(keyPath, writable: true))
            {
                key?.DeleteValue(valueName, throwOnMissingValue: false);
            }
        }
    }
}
