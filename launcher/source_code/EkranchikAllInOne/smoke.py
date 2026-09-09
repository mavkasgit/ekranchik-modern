"""Smoke для EkranchikAllInOne (issue #3 + #4).

Сценарий: сборка (0 warn) → запуск exe с заглушкой backend (/health) и фейковым
киоском → ожидание готовности → запуск киоска → авто-выход по ТОМУ ЖЕ коду
Shutdown(), что висит на пункте трея «Выход». Проверяет логи и маркеры.

Issue #4: persist пяти настроек (allinone_config.json + --dump-config),
применение Excel/OPC UA/симуляции в env сервера, монитора в kiosk_config.json,
--silent без окна, round-trip галки автозапуска в ТЕСТОВОМ ключе реестра
(настоящий Run не пачкается).

Чужое состояние пользователя (allinone_config.json, kiosk_config.json,
HKCU Run) бэкапится ДО прогона и восстанавливается в finally — раннее
исключение не оставляет конфиги битыми и Run удалённым.

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
EXE = HERE / "bin" / "Debug" / "net9.0-windows" / "EkranchikAllInOne.exe"
TMP = HERE / "smoke_tmp"

STUB_BACKEND = '''\
import json, os, sys
from http.server import BaseHTTPRequestHandler, HTTPServer

port = int(sys.argv[sys.argv.index("--port") + 1])
env_dump = sys.argv[sys.argv.index("--env-dump") + 1]
names = ["SIMULATION_ENABLED", "OPCUA_ENDPOINT", "EXCEL_REAL_FILE_PATH",
          "EKRANCHIK_SIMULATION", "EKRANCHIK_OPCUA_ENDPOINT", "EKRANCHIK_EXCEL_PATH"]
with open(env_dump, "w", encoding="utf-8") as f:
    json.dump({n: os.environ.get(n) for n in names}, f, ensure_ascii=False)

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
HTTPServer(("127.0.0.1", port), H).serve_forever()
'''

FAKE_KIOSK = '''\
import sys, time
marker = sys.argv[sys.argv.index("--marker") + 1]
with open(marker, "w") as f:
    f.write(f"fake-kiosk started with args: {sys.argv[1:]}")
print("fake kiosk running", flush=True)
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
                          capture_output=True, text=True, timeout=timeout)


def main() -> int:
    ok = True

    print("== build ==")
    r = subprocess.run(
        ["dotnet", "build", "EkranchikAllInOne.csproj", "-v", "minimal"],
        cwd=HERE, capture_output=True, text=True, timeout=300)
    build_out = (r.stdout or "") + (r.stderr or "")
    ok &= check("build succeeded", r.returncode == 0 and EXE.exists(),
                build_out[-2000:])
    ok &= check("build 0 warnings", "0 Warning(s)" in build_out
                and "warning" not in build_out.lower().replace("0 warning(s)", ""),
                build_out[-2000:])

    if TMP.exists():
        shutil.rmtree(TMP)
    (TMP / "stubdir").mkdir(parents=True)
    (TMP / "stubdir" / "stub_health.py").write_text(STUB_BACKEND, encoding="utf-8")
    (TMP / "fakekiosk").mkdir(parents=True)
    (TMP / "fakekiosk" / "fake_kiosk.py").write_text(FAKE_KIOSK, encoding="utf-8")
    marker = TMP / "kiosk.marker"
    env_dump = TMP / "backend_env.json"

    # --- Issue #4: пять настроек в конфиг-файле (не env — файл главнее кейса).
    TEST_SETTINGS = {
        "ExcelPath": "\\\\test-server\\share\\Учет КПЗ 2026.xlsm",
        "OpcuaEndpoint": "opc.tcp://192.0.2.10:4840/",
        "SimulationEnabled": True,
        "KioskMonitor": 1,
        "AutoStart": False,
    }
    ek_dir = Path(os.environ["LOCALAPPDATA"]) / "Ekranchik"
    ek_dir.mkdir(parents=True, exist_ok=True)
    allinone_cfg = ek_dir / "allinone_config.json"
    kiosk_cfg = ek_dir / "kiosk_config.json"

    # Бэкап чужого состояния ДО любых записей.
    saved_allinone = allinone_cfg.read_bytes() if allinone_cfg.exists() else None
    saved_cfg = kiosk_cfg.read_bytes() if kiosk_cfg.exists() else None
    pre_baks = set(ek_dir.glob("kiosk_config*.bak"))
    # SyncAutoStart при старте трогает настоящий Run только под нашим именем
    # значения (EkranchikAllInOne): бэкапим значение, не весь ключ.
    REAL_RUN = r"HKCU:\Software\Microsoft\Windows\CurrentVersion\Run"
    saved_run = _ps("(Get-ItemPropertyValue "
                    f"-Path '{REAL_RUN}' -Name 'EkranchikAllInOne' -ErrorAction SilentlyContinue)")
    saved_run_value = (saved_run.stdout or "").strip() or None

    TEST_KEY = r"Software\EkranchikAllInOneSmokeTest\Run"
    port = free_port()
    env = dict(os.environ)
    for _k in ("EKRANCHIK_EXCEL_PATH", "EKRANCHIK_OPCUA_ENDPOINT",
               "EKRANCHIK_SIMULATION", "EKRANCHIK_KIOSK_MONITOR", "EKRANCHIK_AUTOSTART"):
        env.pop(_k, None)
    env.update({
        "EKRANCHIK_PYTHON": sys.executable,
        "EKRANCHIK_BACKEND_DIR": str(TMP / "stubdir"),
        "EKRANCHIK_BACKEND_ARGS": f'stub_health.py --port {{port}} --env-dump "{env_dump}"',
        "EKRANCHIK_PORT": str(port),
        "EKRANCHIK_URL": f"http://127.0.0.1:{port}",
        "EKRANCHIK_KIOSK_EXE": sys.executable,
        "EKRANCHIK_KIOSK_ARGS": f'"{TMP / "fakekiosk" / "fake_kiosk.py"}" --marker "{marker}"',
        "EKRANCHIK_READY_TIMEOUT_S": "30",
    })
    CORRUPT = b"{not valid json!!!"

    lingering: list = []
    app_log = ""
    proc = None
    try:
        # Подмена на время прогона (исходники — в бэкапах выше).
        allinone_cfg.write_text(_json.dumps(TEST_SETTINGS, ensure_ascii=False), encoding="utf-8")
        kiosk_cfg.write_bytes(CORRUPT)

        # --- Issue #4: persist пяти настроек через --dump-config (файл, без env). ---
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

        print(f"== run (port {port}) ==")
        # --silent явно: старт в трей без окна, стек поднимается сам.
        proc = subprocess.Popen([str(EXE), "--silent", "--auto-exit-after-ready=3"], env=env)
        try:
            proc.wait(timeout=90)
        except subprocess.TimeoutExpired:
            proc.kill()
            ok &= check("exe exited by itself (no hang/MessageBox)", False, "killed after 90s")
            proc.wait()
        ok &= check("exit code 0", proc.returncode == 0, f"code={proc.returncode}")

        # Даём логам сброситься на диск.
        time.sleep(1)
        logdir = Path(os.environ["LOCALAPPDATA"]) / "Ekranchik" / "logs"
        backends = sorted(logdir.glob("backend-*.log"), key=os.path.getmtime)
        apps = sorted(logdir.glob("allinone-*.log"), key=os.path.getmtime)
        ok &= check("backend log exists", bool(backends))
        ok &= check("allinone log exists", bool(apps))
        backend_log = backends[-1].read_text(encoding="utf-8", errors="replace") if backends else ""
        app_log = apps[-1].read_text(encoding="utf-8", errors="replace") if apps else ""
        ok &= check("backend stub produced output", "stub backend listening" in backend_log)
        ok &= check("backend started", "backend started pid=" in app_log)
        ok &= check("readiness via /health", "backend ready" in app_log)
        ok &= check("kiosk launched", "kiosk started pid=" in app_log)
        ok &= check("shutdown path ran", "shutdown (auto-exit hook)" in app_log and "stopped" in app_log)
        ok &= check("fake kiosk process ran", marker.exists(),
                    "marker file missing — kiosk was not launched")
        ok &= check("no fatal errors", "FATAL" not in app_log)
        # --- Issue #4: применение настроек ---
        ok &= check("--silent without window", "starting silent (no settings window)" in app_log)
        for _k, _v in (("excel", TEST_SETTINGS["ExcelPath"]),
                        ("opcua", TEST_SETTINGS["OpcuaEndpoint"]),
                        ("sim", str(TEST_SETTINGS["SimulationEnabled"])),
                        ("monitor", str(TEST_SETTINGS["KioskMonitor"])),
                        ("autostart", str(TEST_SETTINGS["AutoStart"]))):
            ok &= check(f"settings logged: {_k}", _v in app_log, f"missing {_v!r}")
        try:
            seen_env = _json.loads(env_dump.read_text(encoding="utf-8"))
        except Exception as ex:
            seen_env = {}
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
        try:
            kiosk_after = _json.loads(kiosk_cfg.read_text(encoding="utf-8"))
            ok &= check("monitor applied to kiosk", kiosk_after.get("monitor") == TEST_SETTINGS["KioskMonitor"],
                        f"got={kiosk_after!r}")
        except Exception as ex:
            ok &= check("monitor applied to kiosk", False, str(ex))

        try:
            w = subprocess.run(
                ["powershell", "-NoProfile", "-Command",
                 "Get-CimInstance Win32_Process -Filter \"Name='python.exe'\" | "
                 "Select-Object -ExpandProperty CommandLine"],
                capture_output=True, timeout=60)
            out = (w.stdout or b"").decode("utf-8", errors="replace")
            for needle in ("stub_health.py", "fake_kiosk.py"):
                if needle in out:
                    lingering.append(needle)
        except Exception as ex:
            print(f"[WARN] lingering check skipped: {ex}")
        ok &= check("corrupt config backed up, kiosk still launched",
                    any((p.read_bytes() == CORRUPT)
                        for p in ek_dir.glob("kiosk_config*.corrupt-*.bak") if p not in pre_baks)
                    and "kiosk started pid=" in app_log)
        ok &= check("corrupt raw noted in log", "kiosk config corrupt" in app_log)
        # --- Issue #4: round-trip галки автозапуска в ТЕСТОВОМ ключе реестра. ---
        print("== autostart round-trip (test key only) ==")
        r_on = subprocess.run([str(EXE), "--autostart=on", f"--run-key={TEST_KEY}"],
                              capture_output=True, text=True, timeout=60)
        ok &= check("autostart on exits 0", r_on.returncode == 0, (r_on.stdout + r_on.stderr)[-500:])
        q_on = _ps("(Get-ItemPropertyValue "
                   f"-Path 'HKCU:\\{TEST_KEY}' -Name 'EkranchikAllInOne')")
        ok &= check("autostart value has --silent", q_on.returncode == 0 and "--silent" in (q_on.stdout or ""),
                    (q_on.stdout + q_on.stderr)[-500:])
        r_off = subprocess.run([str(EXE), "--autostart=off", f"--run-key={TEST_KEY}"],
                               capture_output=True, text=True, timeout=60)
        ok &= check("autostart off exits 0", r_off.returncode == 0, (r_off.stdout + r_off.stderr)[-500:])
        q_off = _ps("(Get-ItemPropertyValue "
                    f"-Path 'HKCU:\\{TEST_KEY}' -Name 'EkranchikAllInOne')")
        ok &= check("autostart value removed", q_off.returncode != 0, (q_off.stdout or "")[-300:])
    except Exception as ex:
        ok = check("no unexpected exception", False, f"{ex!r}")
    finally:
        # Exception-safe restore чужого состояния: каждый шаг best-effort.
        if proc is not None:
            try:
                if proc.poll() is None:
                    proc.kill()
                    proc.wait(timeout=30)
            except Exception as ex:
                print(f"[WARN] exe kill failed: {ex}")
        try:
            if saved_cfg is None:
                if kiosk_cfg.exists():
                    kiosk_cfg.unlink()
            else:
                kiosk_cfg.write_bytes(saved_cfg)
            for p in ek_dir.glob("kiosk_config*.bak"):
                if p not in pre_baks:
                    try:
                        p.unlink()
                    except OSError:
                        pass
            tmp_k = ek_dir / "kiosk_config.json.tmp"
            if tmp_k.exists():
                tmp_k.unlink()
        except Exception as ex:
            print(f"[WARN] kiosk restore failed: {ex}")
        try:
            if saved_allinone is None:
                if allinone_cfg.exists():
                    allinone_cfg.unlink()
            else:
                allinone_cfg.write_bytes(saved_allinone)
            tmp_a = ek_dir / "allinone_config.json.tmp"
            if tmp_a.exists():
                tmp_a.unlink()
        except Exception as ex:
            print(f"[WARN] allinone restore failed: {ex}")
        try:
            if saved_run_value is None:
                _ps(f"(Remove-ItemProperty -Path '{REAL_RUN}' -Name 'EkranchikAllInOne' "
                    "-Force -ErrorAction SilentlyContinue)")
            else:
                _ps(f"(Set-ItemProperty -Path '{REAL_RUN}' -Name 'EkranchikAllInOne' "
                    f"-Value '{saved_run_value}')")
        except Exception as ex:
            print(f"[WARN] real Run restore failed: {ex}")
        try:
            _ps("Remove-Item -Path 'HKCU:\\Software\\EkranchikAllInOneSmokeTest' "
                "-Recurse -Force -ErrorAction SilentlyContinue")
        except Exception as ex:
            print(f"[WARN] test key cleanup failed: {ex}")

    # Верификация restore (после finally — видно и при раннем исключении).
    try:
        k_restored = (not kiosk_cfg.exists()) if saved_cfg is None else kiosk_cfg.read_bytes() == saved_cfg
    except Exception:
        k_restored = False
    ok &= check("kiosk_config.json restored", k_restored)
    try:
        a_restored = (not allinone_cfg.exists()) if saved_allinone is None \
            else allinone_cfg.read_bytes() == saved_allinone
    except Exception:
        a_restored = False
    ok &= check("allinone_config.json restored", a_restored)
    leftover = _ps("Test-Path 'HKCU:\\Software\\EkranchikAllInOneSmokeTest'")
    ok &= check("test registry key cleaned", "False" in (leftover.stdout or ""),
                (leftover.stdout or "")[-200:])
    ok &= check("stub processes stopped", not lingering, f"lingering: {lingering}")

    print("SMOKE " + ("PASSED" if ok else "FAILED"))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
