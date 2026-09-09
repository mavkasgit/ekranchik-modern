"""Единый источник версии приложения — корневой файл VERSION.

Бэкенд читает VERSION в рантайме (фолбэк 'dev', если файла нет —
например, в минимальной dev-раскладке). Поиск идёт вверх от этого файла,
поэтому работает и в репозитории (backend/app/core/version.py -> корень),
и в полном пакете (dist-full/backend/VERSION, кладёт build-full-package.ps1).
"""
from functools import lru_cache
from pathlib import Path
from typing import Optional

FALLBACK_VERSION = "dev"


def _find_version_file() -> Optional[Path]:
    for parent in Path(__file__).resolve().parents:
        candidate = parent / "VERSION"
        if candidate.is_file():
            return candidate
    return None


@lru_cache(maxsize=1)
def get_app_version() -> str:
    found = _find_version_file()
    if found is not None:
        try:
            text = found.read_text(encoding="utf-8").strip()
            if text:
                return text.split()[0]
        except OSError:
            pass
    return FALLBACK_VERSION
