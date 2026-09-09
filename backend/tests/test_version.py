"""Версия приложения: единый источник VERSION виден через API.

/api/version отдаёт содержимое корневого VERSION, /health.version —
то же значение живьём (не захардкоженная строка).
"""
from pathlib import Path

from fastapi.testclient import TestClient

import app.main as main_module
from app.core.version import FALLBACK_VERSION, get_app_version


def _expected_version() -> str:
    text = (Path(__file__).resolve().parents[2] / "VERSION").read_text(encoding="utf-8").strip()
    assert text and text != FALLBACK_VERSION
    return text.split()[0]


def test_api_version_matches_version_file():
    client = TestClient(main_module.app, raise_server_exceptions=False)
    resp = client.get("/api/version")
    assert resp.status_code == 200
    assert resp.json() == {"version": _expected_version()}


def test_health_version_is_live():
    client = TestClient(main_module.app, raise_server_exceptions=False)
    resp = client.get("/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "healthy"
    assert body["version"] == get_app_version() == _expected_version()
