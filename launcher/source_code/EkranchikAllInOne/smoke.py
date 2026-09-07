"""Smoke для EkranchikAllInOne (issue #3).

Сценарий: сборка → запуск exe с заглушкой backend (/health) и фейковым
киоском → ожидание готовности → запуск киоска → авто-выход по ТОМУ ЖЕ коду
Shutdown(), что висит на пункте трея «Выход». Проверяет логи и маркеры.

GUI тестируется скриптом, не глазами. Запуск:
    python smoke.py
Требуется: Windows, dotnet, python.
"""
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
import sys
from http.server import BaseHTTPRequestHandler, HTTPServer

port = int(sys.argv[sys.argv.index("--port") + 1])

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


def main() -> int:
    ok = True

    print("== build ==")
    r = subprocess.run(
        ["dotnet", "build", "EkranchikAllInOne.csproj", "-v", "minimal"],
        cwd=HERE, capture_output=True, text=True, timeout=300)
    ok &= check("build succeeded", r.returncode == 0 and EXE.exists(),
                (r.stdout + r.stderr)[-2000:])

    if TMP.exists():
        shutil.rmtree(TMP)
    (TMP / "stubdir").mkdir(parents=True)
    (TMP / "stubdir" / "stub_health.py").write_text(STUB_BACKEND, encoding="utf-8")
    (TMP / "fakekiosk").mkdir(parents=True)
    (TMP / "fakekiosk" / "fake_kiosk.py").write_text(FAKE_KIOSK, encoding="utf-8")
    marker = TMP / "kiosk.marker"

    port = free_port()
    env = dict(os.environ)
    env.update({
        "EKRANCHIK_PYTHON": sys.executable,
        "EKRANCHIK_BACKEND_DIR": str(TMP / "stubdir"),
        "EKRANCHIK_BACKEND_ARGS": f"stub_health.py --port {{port}}",
        "EKRANCHIK_PORT": str(port),
        "EKRANCHIK_URL": f"http://127.0.0.1:{port}",
        "EKRANCHIK_KIOSK_EXE": sys.executable,
        "EKRANCHIK_KIOSK_ARGS": f'"{TMP / "fakekiosk" / "fake_kiosk.py"}" --marker "{marker}"',
        "EKRANCHIK_READY_TIMEOUT_S": "30",
    })
    # Снапшот чужого kiosk_config.json: прогон подменяет URL на время, затем
    # восстанавливает исходник. Битый конфиг — отдельный кейс ниже.
    ek_dir = Path(os.environ["LOCALAPPDATA"]) / "Ekranchik"
    ek_dir.mkdir(parents=True, exist_ok=True)
    kiosk_cfg = ek_dir / "kiosk_config.json"
    saved_cfg = kiosk_cfg.read_bytes() if kiosk_cfg.exists() else None
    pre_baks = set(ek_dir.glob("kiosk_config*.bak"))
    CORRUPT = b"{not valid json!!!"
    kiosk_cfg.write_bytes(CORRUPT)

    print(f"== run (port {port}) ==")
    proc = subprocess.Popen([str(EXE), "--auto-exit-after-ready=3"], env=env)
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

    lingering = []
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
    # Восстановление исходника + уборка созданных прогоном бэкапов.
    try:
        if saved_cfg is None:
            if kiosk_cfg.exists():
                kiosk_cfg.unlink()
        else:
            kiosk_cfg.write_bytes(saved_cfg)
        for p in ek_dir.glob("kiosk_config*.bak"):
            if p not in pre_baks:
                p.unlink()
        if (ek_dir / "kiosk_config.json.tmp").exists():
            (ek_dir / "kiosk_config.json.tmp").unlink()
        restored = (not kiosk_cfg.exists()) if saved_cfg is None else kiosk_cfg.read_bytes() == saved_cfg
    except Exception:
        restored = False
    ok &= check("kiosk_config.json restored", restored)
    ok &= check("stub processes stopped", not lingering, f"lingering: {lingering}")

    print("SMOKE " + ("PASSED" if ok else "FAILED"))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
