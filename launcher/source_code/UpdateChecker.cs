// Общий модуль проверки обновлений: EkranchikKiosk (канал v*) +
// EkranchikAllInOne (канал full-v*). Один файл без нового проекта:
// в киоске лежит рядом с Program.cs (SDK подхватывает сам), в AllInOne —
// линком <Compile Include="..\UpdateChecker.cs" Link="UpdateChecker.cs" />.
// GitHub Releases API без авторизации; без сети — тихий null.
using System;
using System.Diagnostics;
using System.Reflection;
using System.Text;
using System.Net.Http;
using System.Text.Json;
using System.Threading.Tasks;

namespace EkranchikShared
{
    /// <summary>Версия текущего exe: штамп сборки (/p:Version), фолбэк 'dev'.</summary>
    static class AppVersion
    {
        public const string Fallback = "dev";

        public static string Current
        {
            get
            {
                try
                {
                    string? info = Assembly.GetExecutingAssembly()
                        .GetCustomAttribute<AssemblyInformationalVersionAttribute>()?
                        .InformationalVersion;
                    if (!string.IsNullOrWhiteSpace(info))
                        return info.Split('+')[0].Trim();
                    Version? v = Assembly.GetExecutingAssembly().GetName().Version;
                    if (v != null)
                        return v.Revision > 0
                            ? $"{v.Major}.{v.Minor}.{v.Build}.{v.Revision}"
                            : $"{v.Major}.{v.Minor}.{v.Build}";
                }
                catch { }
                return Fallback;
            }
        }
    }

    /// <summary>Минимальный SemVer: сравнение числовых компонент, суффиксы — игнор.</summary>
    static class SemVer
    {
        public static bool TryParse(string? s, out int[] parts)
        {
            parts = Array.Empty<int>();
            if (string.IsNullOrWhiteSpace(s))
                return false;
            string t = s.Trim();
            if (t.StartsWith("v", StringComparison.OrdinalIgnoreCase))
                t = t.Substring(1);
            int cut = t.IndexOfAny(new[] { '-', '+', ' ', '_' });
            if (cut >= 0)
                t = t.Substring(0, cut);
            string[] chunks = t.Split('.');
            if (chunks.Length == 0 || chunks.Length > 4)
                return false;
            var nums = new int[chunks.Length];
            for (int i = 0; i < chunks.Length; i++)
            {
                if (chunks[i].Length == 0 || !int.TryParse(chunks[i], out int n) || n < 0)
                    return false;
                nums[i] = n;
            }
            parts = nums;
            return true;
        }

        public static int Compare(string? a, string? b)
        {
            bool okA = TryParse(a, out int[] pa);
            bool okB = TryParse(b, out int[] pb);
            if (!okA && !okB)
                return 0;
            if (!okA)
                return -1;
            if (!okB)
                return 1;
            int n = Math.Max(pa.Length, pb.Length);
            for (int i = 0; i < n; i++)
            {
                int x = i < pa.Length ? pa[i] : 0;
                int y = i < pb.Length ? pb[i] : 0;
                if (x != y)
                    return x.CompareTo(y);
            }
            return 0;
        }
    }

    /// <summary>Найденное обновление: релиз канала новее текущего + ссылка на ассет.</summary>
    sealed class UpdateInfo
    {
        public UpdateInfo(string tag, string version, string assetName, string assetUrl, long assetSize, string notes)
        {
            Tag = tag;
            Version = version;
            AssetName = assetName;
            AssetUrl = assetUrl;
            AssetSize = assetSize;
            Notes = notes;
        }

        public string Tag { get; }
        public string Version { get; }
        public string AssetName { get; }
        public string AssetUrl { get; }
        /// <summary>Размер ассета из API (0 — неизвестен, проверка пропускается).</summary>
        public long AssetSize { get; }
        public string Notes { get; }
    }

    /// <summary>Проверка GitHub Releases по каналу. Любая ошибка сети/разбора — null.</summary>
    static class UpdateChecker
    {
        public const string RepoOwner = "mavkasgit";
        public const string RepoName = "ekranchik-modern";
        public const string KioskChannelPrefix = "v";
        public const string FullChannelPrefix = "full-v";
        public static readonly TimeSpan Period = TimeSpan.FromHours(6);

        /// <summary>Тег канала: префикс + цифра (v1.0.3 / full-v1.0.3).</summary>
        public static bool IsChannelTag(string? tag, string channelPrefix)
        {
            if (string.IsNullOrWhiteSpace(tag) || string.IsNullOrEmpty(channelPrefix))
                return false;
            if (!tag.StartsWith(channelPrefix, StringComparison.Ordinal))
                return false;
            string rest = tag.Substring(channelPrefix.Length);
            return rest.Length > 0 && char.IsDigit(rest[0]);
        }

        /// <summary>Версия из тега: full-v1.0.3 -&gt; 1.0.3. Строго числовой хвост:
        /// full-v1.0.4-hotfix — null (не предлагать как 1.0.4).</summary>
        public static string? VersionFromTag(string? tag, string channelPrefix)
        {
            if (!IsChannelTag(tag, channelPrefix))
                return null;
            string rest = tag!.Substring(channelPrefix.Length);
            return SemVer.TryParse(rest, out _) && rest.IndexOfAny(new[] { '-', '+', ' ', '_' }) < 0 ? rest : null;
        }

        public static async Task<UpdateInfo?> CheckForUpdateAsync(string currentVersion, string channelPrefix, string assetName)
        {
            try
            {
                string url = $"https://api.github.com/repos/{RepoOwner}/{RepoName}/releases?per_page=50";
                using var http = new HttpClient { Timeout = TimeSpan.FromSeconds(15) };
                http.DefaultRequestHeaders.UserAgent.ParseAdd("Ekranchik-Updater");
                http.DefaultRequestHeaders.Accept.ParseAdd("application/vnd.github+json");
                string json = await http.GetStringAsync(url).ConfigureAwait(false);
                return FindNewer(json, currentVersion, channelPrefix, assetName);
            }
            catch
            {
                return null; // без сети/лимит API — тихий фейл
            }
        }

        /// <summary>Чистая функция поверх JSON релизов: newest СТАБИЛЬНЫЙ релиз канала новее текущего.</summary>
        public static UpdateInfo? FindNewer(string releasesJson, string currentVersion, string channelPrefix, string assetName)
        {
            try
            {
                using JsonDocument doc = JsonDocument.Parse(releasesJson);
                if (doc.RootElement.ValueKind != JsonValueKind.Array)
                    return null;
                UpdateInfo? best = null;
                foreach (JsonElement rel in doc.RootElement.EnumerateArray())
                {
                    if (rel.TryGetProperty("draft", out JsonElement draft) && draft.ValueKind == JsonValueKind.True)
                        continue;
                    // Канал стабильный: пререлизы не предлагаем.
                    if (rel.TryGetProperty("prerelease", out JsonElement pre) && pre.ValueKind == JsonValueKind.True)
                        continue;
                    if (!rel.TryGetProperty("tag_name", out JsonElement tagEl))
                        continue;
                    string? version = VersionFromTag(tagEl.GetString(), channelPrefix);
                    if (version == null || SemVer.Compare(version, currentVersion) <= 0)
                        continue;
                    (string assetUrl, long assetSize, string assetActual) = FindAsset(rel, assetName, version);
                    if (assetUrl.Length == 0)
                        continue;
                    string notes = rel.TryGetProperty("body", out JsonElement body) ? body.GetString() ?? "" : "";
                    var candidate = new UpdateInfo(tagEl.GetString() ?? "", version, assetActual, assetUrl, assetSize, notes);
                    if (best == null || SemVer.Compare(candidate.Version, best.Version) > 0)
                        best = candidate;
                }
                return best;
            }
            catch
            {
                return null;
            }
        }

        /// <summary>Поиск ассета: legacy-имя + маска stem-«версия».exe.
        /// Исключительно: stem в начале + .exe в конце + числовая версия
        /// в середине (мусор вида notes.txt / .exe.bak / чужой префикс мимо).
        /// Приоритет — точному совпадению версии из тега.</summary>
        private static (string Url, long Size, string Name) FindAsset(JsonElement release, string assetName, string version)
        {
            if (!release.TryGetProperty("assets", out JsonElement assets) || assets.ValueKind != JsonValueKind.Array)
                return ("", 0, "");
            string stem = assetName.EndsWith(".exe", StringComparison.OrdinalIgnoreCase)
                ? assetName.Substring(0, assetName.Length - 4)
                : assetName;
            (string u, long s, string n) best = ("", 0, "");
            int bestRank = int.MaxValue;
            foreach (JsonElement asset in assets.EnumerateArray())
            {
                if (!asset.TryGetProperty("name", out JsonElement nameEl))
                    continue;
                string name = nameEl.GetString() ?? "";
                if (!asset.TryGetProperty("browser_download_url", out JsonElement urlEl))
                    continue;
                string dl = urlEl.GetString() ?? "";
                if (dl.Length == 0)
                    continue;
                int rank;
                if (name.Equals(assetName, StringComparison.OrdinalIgnoreCase))
                    rank = 1; // legacy-имя
                else if (IsVersionedAssetName(name, stem, out string embedded))
                    rank = embedded.Equals(version, StringComparison.OrdinalIgnoreCase) ? 0 : 2;
                else
                    continue;
                if (rank >= bestRank)
                    continue;
                long size = 0;
                if (asset.TryGetProperty("size", out JsonElement sizeEl)
                    && sizeEl.ValueKind == JsonValueKind.Number
                    && sizeEl.TryGetInt64(out long num))
                    size = Math.Max(num, 0);
                best = (dl, size, name);
                bestRank = rank;
            }
            return best;
        }

        private static bool IsVersionedAssetName(string name, string stem, out string embedded)
        {
            embedded = "";
            if (!name.StartsWith(stem + "-", StringComparison.OrdinalIgnoreCase)
                || !name.EndsWith(".exe", StringComparison.OrdinalIgnoreCase))
                return false;
            string mid = name.Substring(stem.Length + 1, name.Length - stem.Length - 1 - 4);
            if (!IsStrictVersion(mid))
                return false;
            embedded = mid;
            return true;
        }

        private static bool IsStrictVersion(string s)
        {
            if (string.IsNullOrEmpty(s))
                return false;
            bool dot = false;
            bool digit = false;
            foreach (char c in s)
            {
                if (c == '.')
                    dot = true;
                else if (c >= '0' && c <= '9')
                    digit = true;
                else
                    return false;
            }
            return dot && digit && SemVer.TryParse(s, out _);
        }

        /// <summary>Скачать ассет: потоково в tmp, сверка размера из API, атомарный move.</summary>
        public static async Task<string> DownloadAssetAsync(UpdateInfo update)
        {
            string path = Path.Combine(Path.GetTempPath(),
                "ekranchik-" + Guid.NewGuid().ToString("N") + "-" + update.AssetName);
            string part = path + ".download";
            try
            {
                using (var http = new HttpClient { Timeout = TimeSpan.FromMinutes(15) })
                {
                    http.DefaultRequestHeaders.UserAgent.ParseAdd("Ekranchik-Updater");
                    using var resp = await http.GetAsync(update.AssetUrl,
                        HttpCompletionOption.ResponseHeadersRead).ConfigureAwait(false);
                    resp.EnsureSuccessStatusCode();
                    using var src = await resp.Content.ReadAsStreamAsync().ConfigureAwait(false);
                    using (var dst = new FileStream(part, FileMode.Create, FileAccess.Write,
                        FileShare.None, bufferSize: 81920, useAsync: true))
                    {
                        await src.CopyToAsync(dst).ConfigureAwait(false);
                        await dst.FlushAsync().ConfigureAwait(false);
                    }
                }
                var info = new FileInfo(part);
                if (info.Length == 0)
                    throw new IOException("пустой ассет обновления");
                if (update.AssetSize > 0 && info.Length != update.AssetSize)
                    throw new IOException($"размер ассета {info.Length} != {update.AssetSize} из API");
                File.Move(part, path, overwrite: true);
                return path;
            }
            catch
            {
                try { if (File.Exists(part)) File.Delete(part); } catch { }
                throw;
            }
        }

        /// <summary>Замена установленного киоска: скачать новый exe, положить рядом
        /// updater-cmd (ждёт выхода PID, копирует поверх, рестартит с теми же
        /// аргументами, чистит за собой) и запустить его. Вызыватель после этого
        /// корректно завершает себя. Возвращает путь updater-скрипта (для лога).</summary>
        public static async Task<string> DownloadAndApplyKioskUpdateAsync(
            UpdateInfo update, string installedExePath, string restartArgs)
        {
            string freshExe = await DownloadAssetAsync(update).ConfigureAwait(false);
            int pid = Process.GetCurrentProcess().Id;
            string bat = Path.Combine(Path.GetTempPath(),
                "ekranchik-update-" + Guid.NewGuid().ToString("N") + ".cmd");
            // Все подстановки ниже — внутри двойных кавычек: кавычка гасит
            // метасимволы, но % раскрывается даже в кавычках → удваиваем.
            string qFresh = CmdQuote(freshExe);
            string qInstalled = CmdQuote(installedExePath);
            string qArgs = CmdQuoteArgs(restartArgs);
            string script =
                "@echo off\r\n" +
                "chcp 65001 >nul\r\n" +
                ":wait\r\n" +
                $"tasklist /FI \"PID eq {pid}\" 2>nul | find \"{pid}\" >nul && (timeout /t 1 /nobreak >nul & goto wait)\r\n" +
                $"copy /Y \"{qFresh}\" \"{qInstalled}\" >nul\r\n" +
                $"start \"\" \"{qInstalled}\"{qArgs}\r\n" +
                $"del \"{qFresh}\" >nul 2>&1\r\n" +
                "del \"%~f0\" & exit\r\n";
            File.WriteAllText(bat, script, new System.Text.UTF8Encoding(encoderShouldEmitUTF8Identifier: true));
            Process.Start(new ProcessStartInfo
            {
                FileName = bat,
                UseShellExecute = true,
                WindowStyle = ProcessWindowStyle.Hidden,
                CreateNoWindow = true,
                WorkingDirectory = Path.GetTempPath()
            });
            return bat;
        }

        /// <summary>Значение для подстановки в кавычках .cmd: % удваивается
        /// (раскрывается даже в кавычках), остальные метасимволы внутри
        /// кавычек уже литеральны. Кавычек в путях Windows быть не может.</summary>
        private static string CmdQuote(string value)
        {
            return (value ?? "").Replace("%", "%%");
        }

        /// <summary>Хвост аргументов рестарта: уже поквотирован поаргументно
        /// (см. RestartArgs киоска), здесь только защита от %.</summary>
        private static string CmdQuoteArgs(string value)
        {
            return string.IsNullOrEmpty(value) ? "" : CmdQuote(value);
        }
    }

    /// <summary>Постоянные кейсы shared-модуля: скрытый флаг --self-test обоих exe
    /// (без нового тестового проекта). Возвращает число провалов, пишет лог в tmp.</summary>
    static class UpdateSelfTest
    {
        public static int Run(out string logPath)
        {
            var log = new StringBuilder();
            int failures = 0;
            void Check(bool cond, string name)
            {
                log.AppendLine((cond ? "PASS " : "FAIL ") + name);
                if (!cond)
                    failures++;
            }

            Check(SemVer.Compare("1.0.3", "1.0.3") == 0, "equal");
            Check(SemVer.Compare("1.0.4", "1.0.3") > 0, "patch newer");
            Check(SemVer.Compare("1.0.3", "1.0.10") < 0, "numeric not lexicographic (3 < 10)");
            Check(SemVer.Compare("2.0.0", "1.9.9") > 0, "major wins");
            Check(SemVer.Compare("1.0", "1.0.0") == 0, "missing part is zero");
            Check(SemVer.Compare("v1.0.4", "1.0.3") > 0, "leading v tolerated");
            Check(SemVer.Compare("1.0.4-beta", "1.0.3") > 0, "suffix ignored");

            Check(UpdateChecker.IsChannelTag("v1.0.3", UpdateChecker.KioskChannelPrefix), "kiosk tag v*");
            Check(!UpdateChecker.IsChannelTag("full-v1.0.3", UpdateChecker.KioskChannelPrefix), "full tag not in kiosk channel");

            string renamed = "["
                + "{\"tag_name\": \"full-v1.0.5\", \"draft\": false, \"prerelease\": false, \"body\": \"renamed\","
                + " \"assets\": ["
                + "{\"name\": \"EkranchikSetup-1.0.5.exe\", \"size\": 555,"
                + " \"browser_download_url\": \"https://dl/new/setup-1.0.5.exe\"},"
                + "{\"name\": \"EkranchikSetup.exe\", \"size\": 444,"
                + " \"browser_download_url\": \"https://dl/old/setup.exe\"},"
                + "{\"name\": \"EkranchikSetup-notes.txt\","
                + " \"browser_download_url\": \"https://dl/notes.txt\"},"
                + "{\"name\": \"EkranchikSetup.exe.bak\","
                + " \"browser_download_url\": \"https://dl/bak\"},"
                + "{\"name\": \"MyEkranchikSetup.exe\","
                + " \"browser_download_url\": \"https://dl/evil.exe\"},"
                + "{\"name\": \"EkranchikAllInOne.exe\","
                + " \"browser_download_url\": \"https://dl/other.exe\"}]},"
                + "{\"tag_name\": \"full-v1.0.6\", \"draft\": false, \"prerelease\": false, \"body\": \"garbage only\","
                + " \"assets\": [{\"name\": \"EkranchikSetup-notes.txt\","
                + " \"browser_download_url\": \"https://dl/notes.txt\"}]}"
                + "]";
            var renamedFound = UpdateChecker.FindNewer(renamed, "1.0.3", UpdateChecker.FullChannelPrefix, "EkranchikSetup.exe");
            Check(renamedFound != null && renamedFound.Version == "1.0.5", "versioned asset name matched");
            Check(renamedFound != null && renamedFound.AssetUrl == "https://dl/new/setup-1.0.5.exe", "tag-version match preferred over legacy name");
            Check(renamedFound != null && renamedFound.AssetName == "EkranchikSetup-1.0.5.exe", "actual asset name kept");
            Check(renamedFound != null && renamedFound.AssetSize == 555, "versioned asset size kept");
            Check(UpdateChecker.IsChannelTag("full-v1.0.3", UpdateChecker.FullChannelPrefix), "full tag full-v*");
            Check(!UpdateChecker.IsChannelTag("v1.0.3", UpdateChecker.FullChannelPrefix), "kiosk tag not in full channel");
            Check(!UpdateChecker.IsChannelTag("latest", UpdateChecker.KioskChannelPrefix), "non-version tag rejected");
            Check(!UpdateChecker.IsChannelTag("v", UpdateChecker.KioskChannelPrefix), "bare prefix rejected");
            Check(!UpdateChecker.IsChannelTag(null, UpdateChecker.KioskChannelPrefix), "null rejected");

            Check(UpdateChecker.VersionFromTag("full-v1.0.4", UpdateChecker.FullChannelPrefix) == "1.0.4", "version from full tag");
            Check(UpdateChecker.VersionFromTag("v1.0.4", UpdateChecker.KioskChannelPrefix) == "1.0.4", "version from kiosk tag");
            Check(UpdateChecker.VersionFromTag("full-v1.0.4", UpdateChecker.KioskChannelPrefix) == null, "cross-channel null");
            Check(UpdateChecker.VersionFromTag("full-v1.0.4-hotfix", UpdateChecker.FullChannelPrefix) == null, "hotfix suffix not offered as release");

            string payload = "["
                + "{\"tag_name\": \"full-v1.0.2\", \"draft\": false, \"prerelease\": false, \"body\": \"old\","
                + " \"assets\": [{\"name\": \"EkranchikSetup.exe\", \"size\": 100,"
                + " \"browser_download_url\": \"https://dl/1.0.2/setup.exe\"}]},"
                + "{\"tag_name\": \"v9.9.9\", \"draft\": false, \"prerelease\": false, \"body\": \"kiosk only\","
                + " \"assets\": [{\"name\": \"Ekranchik.exe\","
                + " \"browser_download_url\": \"https://dl/9.9.9/kiosk.exe\"}]},"
                + "{\"tag_name\": \"full-v1.0.10\", \"draft\": false, \"prerelease\": false, \"body\": \"newest\","
                + " \"assets\": [{\"name\": \"EkranchikSetup.exe\", \"size\": 1048576,"
                + " \"browser_download_url\": \"https://dl/1.0.10/setup.exe\"}]},"
                + "{\"tag_name\": \"full-v9.9.9\", \"draft\": false, \"prerelease\": true, \"body\": \"pre skipped\","
                + " \"assets\": [{\"name\": \"EkranchikSetup.exe\", \"size\": 999,"
                + " \"browser_download_url\": \"https://dl/pre/setup.exe\"}]},"
                + "{\"tag_name\": \"full-v1.0.11\", \"draft\": true, \"prerelease\": false, \"body\": \"draft skipped\","
                + " \"assets\": [{\"name\": \"EkranchikSetup.exe\", \"size\": 999,"
                + " \"browser_download_url\": \"https://dl/1.0.11/setup.exe\"}]},"
                + "{\"tag_name\": \"full-v1.0.12-hotfix\", \"draft\": false, \"prerelease\": false, \"body\": \"hotfix skipped\","
                + " \"assets\": [{\"name\": \"EkranchikSetup.exe\", \"size\": 999,"
                + " \"browser_download_url\": \"https://dl/1.0.12/setup.exe\"}]},"
                + "{\"tag_name\": \"full-v1.0.9\", \"draft\": false, \"prerelease\": false, \"body\": \"no asset\","
                + " \"assets\": [{\"name\": \"notes.txt\","
                + " \"browser_download_url\": \"https://dl/notes.txt\"}]}"
                + "]";
            var found = UpdateChecker.FindNewer(payload, "1.0.3", UpdateChecker.FullChannelPrefix, "EkranchikSetup.exe");
            Check(found != null && found.Version == "1.0.10", "newest stable full release picked");
            Check(found != null && found.AssetUrl == "https://dl/1.0.10/setup.exe", "asset url of newest release");
            Check(found != null && found.AssetSize == 1048576, "asset size from api");
            Check(UpdateChecker.FindNewer(payload, "1.0.10", UpdateChecker.FullChannelPrefix, "EkranchikSetup.exe") == null, "no update when current is newest");
            Check(UpdateChecker.FindNewer("not json", "1.0.3", UpdateChecker.FullChannelPrefix, "EkranchikSetup.exe") == null, "broken json -> null");
            var kiosk = UpdateChecker.FindNewer(payload, "1.0.3", UpdateChecker.KioskChannelPrefix, "Ekranchik.exe");
            Check(kiosk != null && kiosk.Version == "9.9.9", "kiosk channel sees only v* releases");

            log.AppendLine(failures == 0 ? "ALL OK" : failures + " FAILURES");
            logPath = Path.Combine(Path.GetTempPath(), "ekranchik-selftest.log");
            try
            {
                File.WriteAllText(logPath, log.ToString());
            }
            catch
            {
                logPath = "";
            }
            return failures;
        }
    }
}
