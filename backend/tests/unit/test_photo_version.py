"""Версия файла фото для `?v=` в URL: пути, отсутствие файла, batch."""

from __future__ import annotations

import logging
import os
from pathlib import Path

import pytest

from app.core.config import settings
from app.services.photo_version import (
    PhotoVersions,
    photo_file_version,
    photo_file_versions,
    photo_versions_for,
)

MTIME_NS = 1_700_000_000_123_456_789


@pytest.fixture
def images(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    root = tmp_path / "static" / "images"
    root.mkdir(parents=True)
    monkeypatch.setattr(settings, "IMAGES_DIR", str(root))
    photo = root / "1010_full.jpg"
    photo.write_bytes(b"photo-bytes")
    os.utime(photo, ns=(MTIME_NS, MTIME_NS))
    return root


def test_images_relative_path_gets_version(images: Path) -> None:
    photo = images / "1010_full.jpg"
    stat = photo.stat()

    assert photo_file_version("images/1010_full.jpg") == f"{stat.st_mtime_ns:x}-{stat.st_size:x}"


def test_static_prefixed_path_resolves_same_file(images: Path) -> None:
    expected = photo_file_version("images/1010_full.jpg")

    assert photo_file_version("/static/images/1010_full.jpg") == expected
    assert photo_file_version("static/images/1010_full.jpg") == expected


def test_windows_separators_resolve_same_file(images: Path) -> None:
    expected = photo_file_version("images/1010_full.jpg")

    assert photo_file_version("images\\1010_full.jpg") == expected


@pytest.mark.parametrize(
    "absolute_path",
    [
        "/app/static/images/1010_full.jpg",
        "C:\\app\\static\\images\\1010_full.jpg",
        "C:/app/static/images/1010_full.jpg",
    ],
)
def test_absolute_paths_are_not_stat_ed(
    images: Path, absolute_path: str, caplog: pytest.LogCaptureFixture
) -> None:
    with caplog.at_level(logging.WARNING, logger="app.services.photo_version"):
        assert photo_file_version(absolute_path) is None

    assert "absolute" in caplog.text


def test_path_escaping_images_root_is_rejected(
    images: Path, caplog: pytest.LogCaptureFixture
) -> None:
    with caplog.at_level(logging.WARNING, logger="app.services.photo_version"):
        assert photo_file_version("images/../../etc/passwd") is None

    assert "escapes" in caplog.text


def test_missing_file_returns_none_and_logs_debug(
    images: Path, caplog: pytest.LogCaptureFixture
) -> None:
    with caplog.at_level(logging.DEBUG, logger="app.services.photo_version"):
        assert photo_file_version("images/missing.jpg") is None

    assert "unavailable" in caplog.text
    assert all(record.levelno < logging.WARNING for record in caplog.records)


def test_external_url_has_no_local_version(images: Path) -> None:
    assert photo_file_version("https://cdn.example.com/1010_full.jpg") is None


def test_empty_path_has_no_version() -> None:
    assert photo_file_version(None) is None
    assert photo_file_version("") is None


def test_single_pair_helper_returns_named_versions(images: Path) -> None:
    thumb = images / "1010_thumb.jpg"
    thumb.write_bytes(b"thumb")
    os.utime(thumb, ns=(MTIME_NS + 1, MTIME_NS + 1))

    versions = photo_versions_for("images/1010_thumb.jpg", "images/1010_full.jpg")

    assert isinstance(versions, PhotoVersions)
    assert versions.thumb is not None
    assert versions.full is not None
    assert versions == photo_file_versions(
        [("images/1010_thumb.jpg", "images/1010_full.jpg")]
    )[0]


def test_batch_versions_align_with_pairs(images: Path) -> None:
    thumb = images / "1010_thumb.jpg"
    thumb.write_bytes(b"thumb")
    os.utime(thumb, ns=(MTIME_NS + 1, MTIME_NS + 1))

    versions = photo_file_versions(
        [
            ("images/1010_thumb.jpg", "images/1010_full.jpg"),
            (None, "images/missing.jpg"),
        ]
    )

    assert versions[0].thumb is not None
    assert versions[0].full is not None
    assert versions[1] == PhotoVersions(None, None)


def test_version_changes_when_file_is_replaced_outside_api(images: Path) -> None:
    """Замена файла мимо API сдвигает версию: кэш `/static/` не залипнет."""
    before = photo_file_version("images/1010_full.jpg")

    os.utime(images / "1010_full.jpg", ns=(MTIME_NS + 1_000_000_000, MTIME_NS + 1_000_000_000))

    assert photo_file_version("images/1010_full.jpg") != before
