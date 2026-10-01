"""
SPA serving tests (ADR 0002, plant machine).

FastAPI serves frontend/dist on the same port when the dist directory
exists, with SPA fallback to index.html. Without dist the legacy
JSON root behaviour is preserved.

Nginx reference (frontend/nginx.conf): proxies /api /ws /static,
SPA fallback via try_files — the same contract is asserted here
against the FastAPI app itself.
"""
import importlib

import pytest
from fastapi.testclient import TestClient

from app.core import config as config_module

INDEX_HTML = "<html><body><div id='root'>SPA</div></body></html>"


def _load_app(monkeypatch, tmp_path, with_dist: bool, with_index: bool = True):
    """Reload app.main with settings pointed at a controlled tmp layout."""
    if with_dist:
        dist = tmp_path / "dist"
        (dist / "assets").mkdir(parents=True)
        if with_index:
            (dist / "index.html").write_text(INDEX_HTML, encoding="utf-8")
        (dist / "assets" / "app.js").write_text("console.log('spa');", encoding="utf-8")
        monkeypatch.setattr(config_module.settings, "FRONTEND_DIST_DIR", str(dist))
    else:
        monkeypatch.setattr(
            config_module.settings, "FRONTEND_DIST_DIR", str(tmp_path / "no-dist")
        )

    static = tmp_path / "static"
    static.mkdir(exist_ok=True)
    (static / "hello.txt").write_text("static-file", encoding="utf-8")
    monkeypatch.setattr(config_module.settings, "STATIC_DIR", str(static))

    import app.main as main_module

    importlib.reload(main_module)
    return TestClient(main_module.app, raise_server_exceptions=False)


@pytest.fixture()
def spa_client(monkeypatch, tmp_path):
    return _load_app(monkeypatch, tmp_path, with_dist=True)


@pytest.fixture()
def api_only_client(monkeypatch, tmp_path):
    return _load_app(monkeypatch, tmp_path, with_dist=False)


@pytest.fixture()
def no_index_client(monkeypatch, tmp_path):
    return _load_app(monkeypatch, tmp_path, with_dist=True, with_index=False)


def test_root_serves_index_html(spa_client):
    resp = spa_client.get("/")
    assert resp.status_code == 200
    assert "text/html" in resp.headers["content-type"]
    assert "SPA" in resp.text


def test_nested_route_falls_back_to_index_html(spa_client):
    resp = spa_client.get("/dashboard/nested")
    assert resp.status_code == 200
    assert "SPA" in resp.text


def test_dist_asset_served(spa_client):
    resp = spa_client.get("/assets/app.js")
    assert resp.status_code == 200
    assert "spa" in resp.text


def test_static_mounted_from_backend(spa_client):
    resp = spa_client.get("/static/hello.txt")
    assert resp.status_code == 200
    assert resp.text == "static-file"


def test_api_namespace_not_shadowed_by_spa(spa_client):
    # Unknown /api path must be JSON 404, never index.html
    resp = spa_client.get("/api/definitely-not-a-route")
    assert resp.status_code == 404
    assert "SPA" not in resp.text
    assert "application/json" in resp.headers["content-type"]


def test_real_api_endpoint_returns_json(spa_client):
    resp = spa_client.get("/api/dashboard/settings")
    assert resp.status_code == 200
    assert "application/json" in resp.headers["content-type"]
    assert "simulation_enabled" in resp.json()

def test_openapi_not_shadowed_by_spa(spa_client):
    resp = spa_client.get("/openapi.json")
    assert resp.status_code == 200
    assert resp.json()["openapi"].startswith("3.")


def test_health_ok_with_dist(spa_client):
    resp = spa_client.get("/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "healthy"


def test_root_returns_json_without_dist(api_only_client):
    resp = api_only_client.get("/")
    assert resp.status_code == 200
    assert "application/json" in resp.headers["content-type"]
    body = resp.json()
    assert body["message"] == "Ekranchik Modern API"
    assert body["health"] == "/health"


def test_health_ok_without_dist(api_only_client):
    resp = api_only_client.get("/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "healthy"

def test_redoc_not_shadowed_by_spa(spa_client):
    resp = spa_client.get("/redoc")
    assert resp.status_code == 200
    assert "SPA" not in resp.text
    assert "text/html" in resp.headers["content-type"]


def test_dist_without_index_falls_back_to_json_root(no_index_client):
    resp = no_index_client.get("/")
    assert resp.status_code == 200
    assert "application/json" in resp.headers["content-type"]
    assert resp.json()["message"] == "Ekranchik Modern API"
