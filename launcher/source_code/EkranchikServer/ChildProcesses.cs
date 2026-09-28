// EkranchikServer — владелец дочерних процессов приложения (ADR 0002, issue #9).
//
// Инвариант: ребёнок, которого запустило приложение, не переживает его смерть —
// даже аварийную (TerminateProcess, «снять задачу»). Держит его kernel Job
// Object с JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE: закрытие последней ссылки на job
// (процесс умер — ОС закрыла handle) убивает всех, кто в job назначен.
//
// Политика задаётся на ребёнка (ChildLifetime): Job — долгоживущий ребёнок
// стека (backend, заглушка в smoke-крючке), Detached — тот, кто обязан
// пережить приложение (установщик обновления).
//
// Отказ ОС (родитель уже в job без вложенности, ограничения UI) не фатален, но
// и не молчалив: строка в лог с кодом Win32, приложение продолжает работу —
// при штатном выходе детей всё равно гасит Stop().

using System;
using System.Diagnostics;
using System.Runtime.InteropServices;

namespace EkranchikServer
{
    enum ChildLifetime
    {
        // В job: умрёт вместе с приложением, включая аварийную смерть.
        Job,

        // Обязан пережить приложение (установщик обновления): стартует через
        // тот же seam, но не назначается в job и не останавливается Stop().
        Detached
    }

    sealed class ChildProcesses
    {
        private readonly RotatingLogger _log;
        private readonly object _lock = new();
        private IntPtr _job = IntPtr.Zero;
        private bool _jobBroken;

        public ChildProcesses(RotatingLogger log)
        {
            _log = log;
        }

        // Единственная точка, где приложение запускает ребёнка:
        // create → configure → start → assign. null — процесс не стартовал.
        public Process? Start(ProcessStartInfo psi, ChildLifetime lifetime, string name,
                              Action<Process>? configure = null)
        {
            try
            {
                var proc = new Process { StartInfo = psi };
                configure?.Invoke(proc);
                if (!proc.Start())
                {
                    _log.Write($"{name} start returned false");
                    return null;
                }
                if (lifetime == ChildLifetime.Job)
                {
                    AssignToJob(proc, name);
                    _log.Write($"{name} started pid={proc.Id}");
                }
                else
                {
                    _log.Write($"{name} started pid={proc.Id} (detached)");
                }
                return proc;
            }
            catch (Exception ex)
            {
                _log.Write($"{name} start failed: {ex.Message}");
                return null;
            }
        }

        // Останавливает ребёнка: мягко, затем дерево процессов. Идемпотентно.
        public void Stop(Process? proc, string name)
        {
            if (proc == null) return;
            try
            {
                if (proc.HasExited)
                {
                    _log.Write($"{name} already exited");
                    return;
                }
                try { proc.CloseMainWindow(); } catch { }
                if (!proc.WaitForExit(3000))
                {
                    try { proc.Kill(entireProcessTree: true); } catch { }
                    proc.WaitForExit(5000);
                }
                _log.Write($"{name} stopped");
            }
            catch
            {
                // Процесс уже мёртв — цель достигнута.
            }
        }

        private void AssignToJob(Process proc, string name)
        {
            try
            {
                lock (_lock)
                {
                    if (_jobBroken)
                    {
                        _log.Write($"WARN: {name} left outside job — job object unavailable");
                        return;
                    }
                    if (_job == IntPtr.Zero)
                    {
                        _job = CreateJobObjectW(IntPtr.Zero, null);
                        if (_job == IntPtr.Zero)
                        {
                            _jobBroken = true;
                            _log.Write($"WARN: {name} outside job — CreateJobObject failed, " +
                                       $"win32={Marshal.GetLastWin32Error()}");
                            return;
                        }
                        var info = new JOBOBJECT_EXTENDED_LIMIT_INFORMATION
                        {
                            BasicLimitInformation = new JOBOBJECT_BASIC_LIMIT_INFORMATION
                            {
                                LimitFlags = JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
                            }
                        };
                        if (!SetInformationJobObject(_job, JobObjectExtendedLimitInformation, ref info,
                                Marshal.SizeOf<JOBOBJECT_EXTENDED_LIMIT_INFORMATION>()))
                        {
                            // Код ошибки снимаем до CloseHandle: она его перетирает.
                            int err = Marshal.GetLastWin32Error();
                            // В job без kill-on-close назначать нельзя — он бы только
                            // ограничивал ребёнка, ничего не гарантируя.
                            CloseHandle(_job);
                            _job = IntPtr.Zero;
                            _jobBroken = true;
                            _log.Write($"WARN: {name} outside job — SetInformationJobObject failed, " +
                                       $"win32={err}");
                            return;
                        }
                    }
                    if (!AssignProcessToJobObject(_job, proc.Handle))
                    {
                        _log.Write($"WARN: {name} outside job — AssignProcessToJobObject failed, " +
                                   $"win32={Marshal.GetLastWin32Error()}");
                        return;
                    }
                    _log.Write($"{name} assigned to job (dies with app)");
                }
            }
            catch (Exception ex)
            {
                // Ребёнок уже стартовал — из-за job-объекта приложение не роняем.
                _log.Write($"WARN: {name} outside job — {ex.Message}");
            }
        }

        private const int JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE = 0x2000;
        // JOBOBJECTINFOCLASS.JobObjectExtendedLimitInformation == 9. Именно этот
        // класс (а не Basic=2) принимает лимиты вроде KILL_ON_JOB_CLOSE: с
        // BASIC-структурой SetInformationJobObject падает win32=87.
        private const int JobObjectExtendedLimitInformation = 9;

        [StructLayout(LayoutKind.Sequential)]
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

        [StructLayout(LayoutKind.Sequential)]
        private struct IO_COUNTERS
        {
            public ulong ReadOperationCount;
            public ulong WriteOperationCount;
            public ulong OtherOperationCount;
            public ulong ReadTransferCount;
            public ulong WriteTransferCount;
            public ulong OtherTransferCount;
        }

        [StructLayout(LayoutKind.Sequential)]
        private struct JOBOBJECT_EXTENDED_LIMIT_INFORMATION
        {
            public JOBOBJECT_BASIC_LIMIT_INFORMATION BasicLimitInformation;
            public IO_COUNTERS IoInfo;
            public UIntPtr ProcessMemoryLimit;
            public UIntPtr JobMemoryLimit;
            public UIntPtr PeakProcessMemoryUsed;
            public UIntPtr PeakJobMemoryUsed;
        }

        // Handle job'а намеренно не закрывается: пока он открыт у живого процесса,
        // job существует; закрытие (в т.ч. ОС при нашей смерти) и есть kill switch.
        [DllImport("kernel32.dll", SetLastError = true)]
        private static extern IntPtr CreateJobObjectW(IntPtr lpJobAttributes, string? lpName);

        [DllImport("kernel32.dll", SetLastError = true)]
        private static extern bool SetInformationJobObject(IntPtr hJob, int infoClass,
                                                          ref JOBOBJECT_EXTENDED_LIMIT_INFORMATION info, int cbSize);

        [DllImport("kernel32.dll", SetLastError = true)]
        private static extern bool AssignProcessToJobObject(IntPtr hJob, IntPtr hProcess);

        [DllImport("kernel32.dll", SetLastError = true)]
        private static extern bool CloseHandle(IntPtr hObject);
    }
}
