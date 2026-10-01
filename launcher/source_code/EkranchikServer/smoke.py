"""Smoke для EkranchikServer (issue #06).

Сценарий: сборка (0 warn) → запуск EkranchikServer.exe с заглушкой backend
(/health) и заглушкой «после готовности» → ожидание готовности → авто-выход по
ТОМУ ЖЕ коду Shutdown(), что висит на пункте трея «Выход». Проверяет логи,
маркеры и гашение детей.

Заглушка после готовности — общего назначения: экран киоска у сервера больше
нет, сервер запускает произвольный процесс через EKRANCHIK_AFTER_READY_EXE /
EKRANCHIK_AFTER_READY_ARGS.

Второй прогон — жёсткий: --crash-after-ready убивает exe через TerminateProcess
(Shutdown/StopProcess в нём не бегут), поэтому заглушек может добить только
kill-on-close job-объекта (ChildProcesses.cs). Проверка — отсутствие живых
python.exe с командной строкой stub_backend.py / after_ready.py после смерти exe.

Третий прогон — занятый порт: сокет держит сам smoke, backend не может
подняться, сервер обязан честно упасть (код 1) и не оставить детей.

Проверяется persist настроек сервера (server_config.json + --dump-config),
применение Excel/OPC UA/симуляции в env сервера, доступ по локалке
(--host 0.0.0.0), --silent без окна, round-trip галки автозапуска в ТЕСТОВОМ
ключе реестра (настоящий Run не пачкается).

Чужое состояние пользователя (server_config.json, значения EkranchikServer и
EkranchikAllInOne в HKCU Run) бэкапится ДО прогона и восстанавливается в
finally — раннее исключение не оставляет конфиг битым и Run изменённым.

GUI тестируется скриптом, не глазами. Запуск:
    python smoke.py
Требуется: Windows, dotnet, python.
"""
import json as _json
import os
import shutil
import socket
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
PROJECT = "EkranchikServer.csproj"
EXE = HERE / "bin" / "Debug" / "net9.0-windows" / "EkranchikServer.exe"
TMP = HERE / "smoke_tmp"

# Живые заглушки ищутся в python.exe по именам файлов.
STUB_NAMES = ("stub_backend.py", "after_ready.py")

STUB_BACKEND = '''\
import json, os, sys
from http.server import BaseHTTPRequestHandler, HTTPServer

port = int(sys.argv[sys.argv.index("--port") + 1])
env_dump = sys.argv[sys.argv.index("--env-dump") + 1]
names = ["SIMULATION_ENABLED", "OPCUA_ENDPOINT", "EXCEL_REAL_FILE_PATH",
         "EKRANCHIK_SIMULATION", "EKRANCHIK_OPCUA_ENDPOINT", "EKRANCHIK_EXCEL_PATH"]
with open(env_dump, "w", encoding="utf-8") as f:
    json.dump({"argv": sys.argv[1:],
               "env": {n: os.environ.get(n) for n in names}}, f, ensure_ascii=False)

class H(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/health":
            body = b'{"status":"ok"}'
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        else:
            self.send_response(404)
            self.end_headers()
    def log_message(self, *a):
        print("stub:", *a, flush=True)

print(f"stub backend listening on {port}", flush=True)
HTTPServer(("0.0.0.0", port), H).serve_forever()
'''

# Заглушка «после готовности» общего назначения: сервер запускает произвольный
# процесс, когда /health ответил (у сервера нет экрана киоска).
AFTER_READY_STUB = '''\
import sys, time
marker = sys.argv[sys.argv.index("--marker") + 1]
with open(marker, "w", encoding="utf-8") as f:
    f.write("after-ready started with args: " + " ".join(sys.argv[1:]))
print("after-ready stub running", flush=True)
time.sleep(300)
'''


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def check(name: str, cond: bool, detail: str = "") -> bool:
    print(f"[{'PASS' if cond else 'FAIL'}] {name}" + (f" — {detail}" if detail and not cond else ""))
    return cond


def _ps(*args: str, timeout: int = 60):
    return subprocess.run(["powershell", "-NoProfile", "-Command", *args],
                          capture_output=True, text=True, timeout=timeout,
                          encoding="utf-8", errors="replace")


def scan_lingering():
    """Живые заглушки в python.exe и exe сервера; None — скан не удался."""
    try:
        w = subprocess.run(
            ["powershell", "-NoProfile", "-Command",
             "Get-CimInstance Win32_Process -Filter \"Name='python.exe'\" | "
             "Select-Object -ExpandProperty CommandLine"],
            capture_output=True, timeout=60)
        out = (w.stdout or b"").decode("utf-8", errors="replace")
        stubs = [n for n in STUB_NAMES if n in out]
        s = subprocess.run(
            ["powershell", "-NoProfile", "-Command",
             "Get-CimInstance Win32_Process -Filter \"Name='EkranchikServer.exe'\" | "
             "Select-Object -ExpandProperty ProcessId"],
            capture_output=True, timeout=60)
        servers = [n for n in (s.stdout or b"").decode("utf-8", errors="replace").split() if n.strip()]
        return {"stubs": stubs, "servers": servers}
    except Exception as ex:
        print(f"[WARN] lingering check failed: {ex}")
        return None


def _log_slice(path: Path, offset: int) -> str:
    """Хвост лога после offset: дневной лог копится между запусками (в т.ч.
    чужими), ассерты смотрят только секцию от своего смещения."""
    if not path.exists():
        return ""
    return path.read_bytes()[offset:].decode("utf-8", errors="replace")


def main() -> int:
    ok = True

    print("== build ==")
    # Локаль машины не должна ломать прогон: dotnet по умолчанию печатает
    # по-русски в однобайтовой кодировке (UnicodeDecodeError в readerthread),
    # а проверки ниже ищут английские строки сборки.
    build_env = dict(os.environ, DOTNET_CLI_UI_LANGUAGE="en")
    r = subprocess.run(
        ["dotnet", "build", PROJECT, "-v", "minimal"],
        cwd=HERE, capture_output=True, text=True, timeout=300, env=build_env,
        encoding="utf-8", errors="replace")
    build_out = (r.stdout or "") + (r.stderr or "")
    ok &= check("build succeeded", r.returncode == 0 and EXE.exists(),
                build_out[-2000:])
    ok &= check("build 0 warnings", r.returncode == 0 and "0 Warning(s)" in build_out
                and "warning" not in build_out.lower().replace("0 warning(s)", ""),
                build_out[-2000:])

    # Приложения однопользовательские (мьютексы Local\EkranchikServer и
    # Local\Ekranchik): второй экземпляр тихо выходит, и прогон прошёл бы
    # вхолостую. Снимаем любой живой экземпляр (в том числе установленный) —
    # прогон должен владеть стеком.
    _ps("Get-Process -Name 'EkranchikServer','Ekranchik','EkranchikAllInOne' "
        "-ErrorAction SilentlyContinue | Stop-Process -Force")
    time.sleep(1)
    if TMP.exists():
        # ignore_errors: после провала hard-kill прогона в заглушках могут ещё
        # жить недобитые процессы — следующий прогон не должен падать об это.
        shutil.rmtree(TMP, ignore_errors=True)
    (TMP / "stubdir").mkdir(parents=True)
    (TMP / "stubdir" / "stub_backend.py").write_text(STUB_BACKEND, encoding="utf-8")
    (TMP / "hookdir").mkdir(parents=True)
    (TMP / "hookdir" / "after_ready.py").write_text(AFTER_READY_STUB, encoding="utf-8")
    marker = TMP / "after_ready.marker"
    env_dump = TMP / "backend_env.json"
    busy_env_dump = TMP / "backend_env_busy.json"

    # --- Настройки в конфиг-файле (не env — файл главнее кейса).
    TEST_SETTINGS = {
        "ExcelPath": "\\\\test-server\\share\\Учет КПЗ 2026.xlsm",
        "OpcuaEndpoint": "opc.tcp://192.0.2.10:4840/",
        "SimulationEnabled": True,
        "LanAccess": True,
        "AutoStart": False,
    }
    ek_dir = Path(os.environ["LOCALAPPDATA"]) / "Ekranchik"
    ek_dir.mkdir(parents=True, exist_ok=True)
    server_cfg = ek_dir / "server_config.json"

    # Бэкап чужого состояния ДО любых записей.
    saved_server_cfg = server_cfg.read_bytes() if server_cfg.exists() else None
    # SyncAutoStart при старте трогает настоящий Run только под нашим именем
    # значения (EkranchikServer), миграция удаляет устаревшее
    # значение прежней поставки — бэкапим оба значения, не весь ключ.
    REAL_RUN = r"HKCU:\Software\Microsoft\Windows\CurrentVersion\Run"
    saved_run = _ps("(Get-ItemPropertyValue "
                    f"-Path '{REAL_RUN}' -Name 'EkranchikServer' -ErrorAction SilentlyContinue)")
    saved_run_value = (saved_run.stdout or "").strip() or None
    saved_legacy_run = _ps("(Get-ItemPropertyValue "
                           f"-Path '{REAL_RUN}' -Name 'EkranchikAllInOne' -ErrorAction SilentlyContinue)")
    saved_legacy_run_value = (saved_legacy_run.stdout or "").strip() or None

    TEST_KEY = r"Software\EkranchikServerSmokeTest\Run"
    RUN_VALUE = "EkranchikServer"
    port = free_port()
    env = dict(os.environ)
    for _k in ("EKRANCHIK_EXCEL_PATH", "EKRANCHIK_OPCUA_ENDPOINT",
               "EKRANCHIK_SIMULATION", "EKRANCHIK_AUTOSTART",
               "EKRANCHIK_LAN_ACCESS", "EKRANCHIK_AFTER_READY_EXE",
               "EKRANCHIK_AFTER_READY_ARGS"):
        env.pop(_k, None)
    env.update({
        "EKRANCHIK_PYTHON": sys.executable,
        "EKRANCHIK_BACKEND_DIR": str(TMP / "stubdir"),
        # --host/--port добавляет сам exe (LanAccess/Port) — в аргументах их нет.
        "EKRANCHIK_BACKEND_ARGS": f'stub_backend.py --env-dump "{env_dump}"',
        "EKRANCHIK_PORT": str(port),
        "EKRANCHIK_URL": f"http://127.0.0.1:{port}",
        "EKRANCHIK_AFTER_READY_EXE": sys.executable,
        "EKRANCHIK_AFTER_READY_ARGS":
            f'"{TMP / "hookdir" / "after_ready.py"}" --marker "{marker}"',
        "EKRANCHIK_READY_TIMEOUT_S": "30",
    })

    logs_dir = ek_dir / "logs"
    today = logs_dir / time.strftime("server-%Y%m%d.log")
    today_backend = logs_dir / time.strftime("backend-%Y%m%d.log")

    lingering = None
    procs: list = []
    try:
        # Подмена на время прогона (исходник — в бэкапе выше).
        server_cfg.write_text(_json.dumps(TEST_SETTINGS, ensure_ascii=False), encoding="utf-8")

        # --- Persist настроек сервера через --dump-config (файл, без env). ---
        print("== dump-config (persist) ==")
        d = subprocess.run([str(EXE), "--dump-config"], env=env,
                           capture_output=True, text=True, timeout=60)
        dumped = {}
        try:
            dumped = _json.loads((d.stdout or "").strip().splitlines()[-1])
        except Exception as ex:
            ok &= check("dump-config is valid JSON", False, f"{ex}: {(d.stdout or '')[-500:]}")
        else:
            ok &= check("dump-config exit 0", d.returncode == 0, f"code={d.returncode}")
            for k, v in TEST_SETTINGS.items():
                ok &= check(f"setting persists: {k}", dumped.get(k) == v,
                            f"file={v!r} got={dumped.get(k)!r}")
        # Env-переопределение перекрывает файл (EKRANCHIK_SIMULATION=false).
        env2 = dict(env, EKRANCHIK_SIMULATION="false",
                    EKRANCHIK_OPCUA_ENDPOINT="opc.tcp://192.0.2.20:4840/")
        d2 = subprocess.run([str(EXE), "--dump-config"], env=env2,
                            capture_output=True, text=True, timeout=60)
        try:
            dumped2 = _json.loads((d2.stdout or "").strip().splitlines()[-1])
        except Exception as ex:
            ok &= check("dump-config env override is JSON", False, str(ex))
        else:
            ok &= check("env overrides file (simulation)", dumped2.get("SimulationEnabled") is False,
                        f"got={dumped2.get('SimulationEnabled')!r}")
            ok &= check("env overrides file (opcua)", dumped2.get("OpcuaEndpoint") == "opc.tcp://192.0.2.20:4840/",
                        f"got={dumped2.get('OpcuaEndpoint')!r}")

        # Изоляция прогона: дневные логи копятся между запусками (в т.ч.
        # чужими) — все ассерты ниже смотрят только секцию от этого смещения.
        pre_log_size = today.stat().st_size if today.exists() else 0
        print(f"== run (port {port}) ==")
        # --silent явно: старт в трей без окна, стек поднимается сам.
        proc = subprocess.Popen([str(EXE), "--silent", "--auto-exit-after-ready=3"], env=env)
        procs.append(proc)
        try:
            proc.wait(timeout=90)
        except subprocess.TimeoutExpired:
            proc.kill()
            ok &= check("exe exited by itself (no hang/MessageBox)", False, "killed after 90s")
            proc.wait()
        ok &= check("exit code 0", proc.returncode == 0, f"code={proc.returncode}")

        # Даём логам сброситься на диск.
        time.sleep(1)
        backend_log = _log_slice(today_backend, 0) if today_backend.exists() else ""
        backends = sorted(logs_dir.glob("backend-*.log"), key=os.path.getmtime)
        apps = sorted(logs_dir.glob("server-*.log"), key=os.path.getmtime)
        ok &= check("backend log exists", bool(backends))
        ok &= check("server log exists", bool(apps))
        app_log = _log_slice(today, pre_log_size)
        ok &= check("backend stub produced output", "stub backend listening" in backend_log)
        ok &= check("backend started", "backend started pid=" in app_log)
        ok &= check("readiness via /health", "backend ready" in app_log)
        ok &= check("after-ready hook launched", "after-ready started pid=" in app_log)
        ok &= check("shutdown path ran", "shutdown (auto-exit hook)" in app_log and "stopped" in app_log)
        ok &= check("after-ready stub process ran", marker.exists(),
                    "marker file missing — the hook was not launched")
        ok &= check("no fatal errors", "FATAL" not in app_log, app_log[-500:])
        ok &= check("--silent without window", "starting silent (no settings window)" in app_log)
        # Настройки сервера прочитаны из server_config.json после разделения
        # приложений и доехали до окружения backend.
        ok &= check("settings read from server_config.json",
                    f"excel={TEST_SETTINGS['ExcelPath']}" in app_log
                    and f"opcua={TEST_SETTINGS['OpcuaEndpoint']}" in app_log
                    and f"lan={TEST_SETTINGS['LanAccess']}" in app_log,
                    app_log[-800:])
        for _k, _v in (("excel", TEST_SETTINGS["ExcelPath"]),
                       ("opcua", TEST_SETTINGS["OpcuaEndpoint"]),
                       ("sim", str(TEST_SETTINGS["SimulationEnabled"])),
                       ("autostart", str(TEST_SETTINGS["AutoStart"]))):
            ok &= check(f"settings logged: {_k}", _v in app_log, f"missing {_v!r}")
        try:
            dump = _json.loads(env_dump.read_text(encoding="utf-8"))
            seen_env = dump.get("env") or {}
            seen_argv = " ".join(dump.get("argv") or [])
        except Exception as ex:
            seen_env, seen_argv = {}, ""
            ok &= check("backend env dump exists", False, str(ex))
        else:
            ok &= check("simulation applied to backend env",
                        seen_env.get("SIMULATION_ENABLED") == "true" and seen_env.get("EKRANCHIK_SIMULATION") == "true",
                        f"got={seen_env!r}")
            ok &= check("opcua applied to backend env",
                        seen_env.get("OPCUA_ENDPOINT") == TEST_SETTINGS["OpcuaEndpoint"]
                        and seen_env.get("EKRANCHIK_OPCUA_ENDPOINT") == TEST_SETTINGS["OpcuaEndpoint"],
                        f"got={seen_env!r}")
            ok &= check("excel applied to backend env",
                        seen_env.get("EXCEL_REAL_FILE_PATH") == TEST_SETTINGS["ExcelPath"]
                        and seen_env.get("EKRANCHIK_EXCEL_PATH") == TEST_SETTINGS["ExcelPath"],
                        f"got={seen_env!r}")
            # LanAccess=true → сервер слушает все интерфейсы (доступ с других ПК).
            ok &= check("lan access binds 0.0.0.0",
                        "--host 0.0.0.0" in seen_argv and "--host 0.0.0.0" in app_log,
                        f"argv={seen_argv!r}")

        lingering = scan_lingering()
        ok &= check("children stopped on graceful exit",
                    lingering is not None and lingering["stubs"] == [],
                    "scan failed" if lingering is None else f"lingering: {lingering}")

        # --- Job Object: аварийная смерть приложения не оставляет детей.
        #     --crash-after-ready убивает exe через TerminateProcess: Shutdown и
        #     StopProcess в этом прогоне не бегут, значит заглушек может добить
        #     только kill-on-close самого job-объекта.
        print("== hard-kill run (job object) ==")
        crash_pre = today.stat().st_size if today.exists() else 0
        crash = subprocess.Popen([str(EXE), "--silent", "--crash-after-ready=2"], env=env)
        procs.append(crash)
        try:
            crash.wait(timeout=90)
        except subprocess.TimeoutExpired:
            crash.kill()
            crash.wait(timeout=30)
            ok &= check("crash run finished by itself", False, "killed after 90s")
        time.sleep(1)
        crash_log = _log_slice(today, crash_pre)
        ok &= check("crash run: backend started", "backend started pid=" in crash_log)
        ok &= check("crash run: after-ready launched", "after-ready started pid=" in crash_log)
        ok &= check("crash run: no graceful shutdown",
                    "smoke hook: Process.Kill" in crash_log and "shutdown (" not in crash_log,
                    crash_log[-500:])
        crash_lingering = None
        for _ in range(20):  # kill-on-close асинхронен — до 10 с
            crash_lingering = scan_lingering()
            if crash_lingering is not None and crash_lingering["stubs"] == []:
                break
            time.sleep(0.5)
        ok &= check("hard kill: job killed stub children",
                    crash_lingering is not None and crash_lingering["stubs"] == [],
                    "scan failed" if crash_lingering is None else f"lingering: {crash_lingering}")

        # --- Занятый порт: backend не подняться, сервер обязан упасть, а не
        #     висеть с модальным окном и живыми детьми. ---
        print("== occupied port run ==")
        busy_port = free_port()
        busy_env = dict(env, EKRANCHIK_PORT=str(busy_port),
                        EKRANCHIK_URL=f"http://127.0.0.1:{busy_port}",
                        EKRANCHIK_BACKEND_ARGS=f'stub_backend.py --env-dump "{busy_env_dump}"')
        busy_pre = today.stat().st_size if today.exists() else 0
        holder = socket.socket()
        # Windows: без SO_EXCLUSIVEADDRUSE чужой сокет с SO_REUSEADDR (его
        # ставит любой http.server) всё равно забиндит тот же порт — «занятость»
        # проверки тогда не возникает. Exclusive держит порт по-настоящему.
        holder.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        holder.bind(("0.0.0.0", busy_port))
        holder.listen(1)
        try:
            busy = subprocess.Popen([str(EXE), "--silent"], env=busy_env)
            procs.append(busy)
            try:
                busy.wait(timeout=60)
            except subprocess.TimeoutExpired:
                busy.kill()
                busy.wait(timeout=30)
                ok &= check("busy port run finished by itself", False, "killed after 60s")
            busy_code = busy.returncode
        finally:
            holder.close()
        time.sleep(1)
        busy_log = _log_slice(today, busy_pre)
        ok &= check("busy port: backend started", "backend started pid=" in busy_log)
        ok &= check("busy port: fails with exit 1", busy_code == 1, f"code={busy_code}")
        ok &= check("busy port: explains the failure",
                    "FATAL" in busy_log
                    and ("backend exited early" in busy_log
                         or "backend not ready" in busy_log),
                    busy_log[-500:])
        ok &= check("busy port: after-ready hook not launched",
                    "after-ready started" not in busy_log, busy_log[-500:])
        busy_lingering = None
        for _ in range(20):
            busy_lingering = scan_lingering()
            if busy_lingering is not None and busy_lingering["stubs"] == []:
                break
            time.sleep(0.5)
        ok &= check("busy port: no children left",
                    busy_lingering is not None and busy_lingering["stubs"] == [],
                    "scan failed" if busy_lingering is None else f"lingering: {busy_lingering}")

        # --- Round-trip галки автозапуска в ТЕСТОВОМ ключе реестра. ---
        print("== autostart round-trip (test key only) ==")
        r_on = subprocess.run([str(EXE), "--autostart=on", f"--run-key={TEST_KEY}"],
                              capture_output=True, text=True, timeout=60)
        ok &= check("autostart on exits 0", r_on.returncode == 0, (r_on.stdout + r_on.stderr)[-500:])
        q_on = _ps("(Get-ItemPropertyValue "
                   f"-Path 'HKCU:\\{TEST_KEY}' -Name '{RUN_VALUE}')")
        ok &= check("autostart value has --silent", q_on.returncode == 0 and "--silent" in (q_on.stdout or ""),
                    (q_on.stdout + q_on.stderr)[-500:])
        r_off = subprocess.run([str(EXE), "--autostart=off", f"--run-key={TEST_KEY}"],
                               capture_output=True, text=True, timeout=60)
        ok &= check("autostart off exits 0", r_off.returncode == 0, (r_off.stdout + r_off.stderr)[-500:])
        q_off = _ps("(Get-ItemPropertyValue "
                    f"-Path 'HKCU:\\{TEST_KEY}' -Name '{RUN_VALUE}')")
        ok &= check("autostart value removed", q_off.returncode != 0, (q_off.stdout or "")[-300:])
    except Exception as ex:
        ok = check("no unexpected exception", False, f"{ex!r}")
    finally:
        # Exception-safe restore чужого состояния: каждый шаг best-effort.
        for p in procs:
            try:
                if p.poll() is None:
                    p.kill()
                    p.wait(timeout=30)
            except Exception as ex:
                print(f"[WARN] exe kill failed: {ex}")
        try:
            if saved_server_cfg is None:
                if server_cfg.exists():
                    server_cfg.unlink()
            else:
                server_cfg.write_bytes(saved_server_cfg)
            tmp_a = ek_dir / "server_config.json.tmp"
            if tmp_a.exists():
                tmp_a.unlink()
        except Exception as ex:
            print(f"[WARN] server config restore failed: {ex}")
        for _name, _saved in (("EkranchikServer", saved_run_value),
                              ("EkranchikAllInOne", saved_legacy_run_value)):
            try:
                if _saved is None:
                    _ps(f"(Remove-ItemProperty -Path '{REAL_RUN}' -Name '{_name}' "
                        "-Force -ErrorAction SilentlyContinue)")
                else:
                    _ps(f"(Set-ItemProperty -Path '{REAL_RUN}' -Name '{_name}' "
                        f"-Value '{_saved}')")
            except Exception as ex:
                print(f"[WARN] Run restore {_name} failed: {ex}")
        try:
            _ps("Remove-Item -Path 'HKCU:\\Software\\EkranchikServerSmokeTest' "
                "-Recurse -Force -ErrorAction SilentlyContinue")
        except Exception as ex:
            print(f"[WARN] test key cleanup failed: {ex}")

    # Верификация restore (после finally — видно и при раннем исключении).
    try:
        s_restored = (not server_cfg.exists()) if saved_server_cfg is None \
            else server_cfg.read_bytes() == saved_server_cfg
    except Exception:
        s_restored = False
    ok &= check("server_config.json restored", s_restored)
    now_run = _ps("(Get-ItemPropertyValue "
                  f"-Path '{REAL_RUN}' -Name '{RUN_VALUE}' -ErrorAction SilentlyContinue)")
    now_run_value = (now_run.stdout or "").strip() or None
    ok &= check("real Run EkranchikServer restored", now_run_value == saved_run_value,
                f"saved={saved_run_value!r} now={now_run_value!r}")
    leftover = _ps("Test-Path 'HKCU:\\Software\\EkranchikServerSmokeTest'")
    ok &= check("test registry key cleaned", "False" in (leftover.stdout or ""),
                (leftover.stdout or "")[-200:])
    final = scan_lingering()
    ok &= check("no processes left behind",
                final is not None and not final["stubs"] and not final["servers"],
                "scan failed" if final is None else f"lingering: {final}")

    print("SMOKE " + ("PASSED" if ok else "FAILED"))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
