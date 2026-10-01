"""
Application configuration using Pydantic Settings

Заводская машина без Docker (ADR 0002): данные (SQLite + images)
живут в %LOCALAPPDATA%/Ekranchik/data и переживают переустановку.
Правила разрешения (dev/Docker не ломаются):
  DATABASE_URL / IMAGES_DIR, заданные явно (env, .env, compose) — всегда win.
  Иначе: EKRANCHIK_DATA_DIR > %LOCALAPPDATA%/Ekranchik/data > ./data-фолбэк.
Настройки пробрасываются env-алиасами EKRANCHIK_*: EKRANCHIK_EXCEL_PATH,
EKRANCHIK_OPCUA_ENDPOINT, EKRANCHIK_SIMULATION. Голые имена в приоритете
над алиасами.
"""
import os
from pathlib import Path
from typing import List, Optional
from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


def default_data_dir() -> Optional[Path]:
    """Каталог данных заводской машины или None (dev/Docker-фолбэк)."""
    override = os.environ.get("EKRANCHIK_DATA_DIR")
    if override:
        return Path(override)
    local = os.environ.get("LOCALAPPDATA")
    if local:
        return Path(local) / "Ekranchik" / "data"
    return None


class Settings(BaseSettings):
    """Application settings loaded from environment variables"""
    
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore"
    )
    
    # Application
    ENVIRONMENT: str = "development"
    DEBUG: bool = True
    
    # Server
    HOST: str = "0.0.0.0"
    PORT: int = 8000
    
    # Database
    DATABASE_URL: str = "sqlite+aiosqlite:///./data/ekranchik.db"
    
    # CORS
    CORS_ORIGINS: List[str] = ["http://localhost:3000", "http://localhost:5173"]
    
    # --- Simulation Switch ---
    SIMULATION_ENABLED: bool = False # Set to True to use simulated OPC UA and test Excel file

    # --- OPC UA Configuration ---
    OPCUA_ENABLED: bool = True # Master switch to enable/disable OPC UA service
    OPCUA_ENDPOINT: str = "opc.tcp://172.17.11.115:4840/"
    OPCUA_SIM_ENDPOINT: str = "opc.tcp://127.0.0.1:4840/freeopcua/server/" # Simulator endpoint
    OPCUA_POLL_INTERVAL: int = 5  # Seconds between polls for real server
    OPCUA_SIM_POLL_INTERVAL: int = 1  # Seconds between polls for simulation

    # Excel file paths
    EXCEL_REAL_FILE_PATH: str = "//ktm-disk/Оператор/Учет КПЗ 2026.xlsm"
    EXCEL_TEST_FILE_PATH: str = "../testdata/Учет КПЗ 2026.xlsm"
    # Файл с последним введённым путём к книге. Имя настраивается, потому что
    # каталог static у dev-бэкенда и прод-контейнера — один и тот же: с общим
    # именем выбор одной среды подменяет книгу другой (путь контейнера
    # `/app/excel/…` против UNC-пути dev-хоста).
    EXCEL_ACTIVE_FILE_NAME: str = "active_excel.json"
    
    # Static files
    STATIC_DIR: str = "../static"  # Relative to backend folder
    IMAGES_DIR: str = "../static/images"

    # Frontend SPA (ADR 0002): FastAPI serves frontend/dist on the same port
    FRONTEND_DIST_DIR: str = "../frontend/dist"  # Relative to backend folder

    # Overrides from the server settings UI (EKRANCHIK_* contract).
    # Applied in the validator below ONLY when the bare name was not
    # provided explicitly (env/.env/compose win over aliases).
    EKRANCHIK_DATA_DIR: Optional[str] = None
    EKRANCHIK_EXCEL_PATH: Optional[str] = None
    EKRANCHIK_OPCUA_ENDPOINT: Optional[str] = None
    EKRANCHIK_SIMULATION: Optional[bool] = None

    @model_validator(mode="after")
    def _apply_plant_defaults(self):
        """Разрешить каталог данных и EKRANCHIK_*-алиасы (ADR 0002)."""
        provided = self.model_fields_set
        if self.EKRANCHIK_SIMULATION is not None and "SIMULATION_ENABLED" not in provided:
            self.SIMULATION_ENABLED = self.EKRANCHIK_SIMULATION
        if self.EKRANCHIK_OPCUA_ENDPOINT and "OPCUA_ENDPOINT" not in provided:
            self.OPCUA_ENDPOINT = self.EKRANCHIK_OPCUA_ENDPOINT
        if self.EKRANCHIK_EXCEL_PATH and "EXCEL_REAL_FILE_PATH" not in provided:
            self.EXCEL_REAL_FILE_PATH = self.EKRANCHIK_EXCEL_PATH
        data_dir = Path(self.EKRANCHIK_DATA_DIR) if self.EKRANCHIK_DATA_DIR else default_data_dir()
        if data_dir is not None:
            if "DATABASE_URL" not in provided:
                self.DATABASE_URL = "sqlite+aiosqlite:///" + (data_dir / "ekranchik.db").as_posix()
            if "IMAGES_DIR" not in provided:
                self.IMAGES_DIR = (data_dir / "images").as_posix()
        return self

    @property
    def data_dir_path(self) -> Path:
        """Каталог данных: родитель sqlite-файла (создаётся при старте)."""
        url = self.DATABASE_URL
        for prefix in ("sqlite+aiosqlite:///", "sqlite:///"):
            if url.startswith(prefix):
                return Path(url[len(prefix):]).parent
        return default_data_dir() or Path("./data")

    # Журнал подвесов (issue #34): файл с историей проходов по линии.
    # Каталог выводится из data_dir_path, то есть в контейнере это
    # примонтированный том, а в exe — каталог данных. Отдельно
    # переопределяется только если каталог данных не подходит.
    JOURNAL_DIR: Optional[str] = None
    JOURNAL_RETENTION_DAYS: int = 30
    JOURNAL_MAX_FILE_BYTES: int = 32 * 1024 * 1024
    JOURNAL_FLUSH_INTERVAL: int = 30

    @property
    def journal_dir_path(self) -> Path:
        """Каталог файлов журнала подвесов (создаётся при первой записи)."""
        if self.JOURNAL_DIR:
            return Path(self.JOURNAL_DIR)
        return self.data_dir_path / "journal"
    
    # Photo upload
    MAX_UPLOAD_SIZE: int = 10 * 1024 * 1024  # 10MB
    THUMBNAIL_SIZE: tuple = (200, 200)
    
    @property
    def excel_active_file_name(self) -> str:
        """Имя файла выбора активной книги; в симуляции — вариант с ``_sim``.

        Имя задаёт конфигурация (``EXCEL_ACTIVE_FILE_NAME``), чтобы dev и
        прод-контейнер на одной машине не переписывали выбор друг друга в
        общем каталоге `static`. Суффикс ``_sim`` вставляется перед
        расширением: ``active_excel_prod.json`` → ``active_excel_prod_sim.json``.
        """
        name = Path(self.EXCEL_ACTIVE_FILE_NAME)
        if not self.SIMULATION_ENABLED:
            return name.name
        return f"{name.stem}_sim{name.suffix}"

    @property
    def excel_path(self) -> Path | None:
        """Get Excel file path as Path object"""
        if self.SIMULATION_ENABLED:
            return Path(self.EXCEL_TEST_FILE_PATH) if self.EXCEL_TEST_FILE_PATH else None
        else:
            return Path(self.EXCEL_REAL_FILE_PATH) if self.EXCEL_REAL_FILE_PATH else None
    
    @property
    def images_path(self) -> Path:
        """Get images directory path"""
        return Path(self.IMAGES_DIR)
    
    @property
    def STATIC_PATH(self) -> Path | None:
        """Get static directory path"""
        path = Path(self.STATIC_DIR)
        if path.exists():
            return path
        return None

    @property
    def FRONTEND_DIST_PATH(self) -> Path | None:
        """Get frontend dist directory path"""
        candidates = [Path(self.FRONTEND_DIST_DIR)]
        # Пакет заводской машины: <pkg>/backend + <pkg>/dist (CWD = backend/).
        backend_dir = Path(__file__).resolve().parents[2]
        candidates.append(backend_dir.parent / "dist")
        for path in candidates:
            if path.exists():
                return path
        return None

    def update_simulation_mode_in_env(self, enabled: bool) -> None:
        """Обновляет значение SIMULATION_ENABLED в файле .env"""
        env_file = Path(".env")
        if not env_file.exists():
            for p in [Path("../.env"), Path("backend/.env"), Path("backend/app/.env")]:
                if p.exists():
                    env_file = p
                    break
        
        if env_file.exists():
            try:
                with open(env_file, 'r', encoding='utf-8') as f:
                    lines = f.readlines()
                
                found = False
                for i, line in enumerate(lines):
                    if line.strip().startswith('SIMULATION_ENABLED='):
                        lines[i] = f"SIMULATION_ENABLED={'true' if enabled else 'false'}\n"
                        found = True
                        break
                
                if not found:
                    lines.append(f"\nSIMULATION_ENABLED={'true' if enabled else 'false'}\n")
                
                with open(env_file, 'w', encoding='utf-8') as f:
                    f.writelines(lines)
            except Exception as e:
                import logging
                logging.getLogger(__name__).error(f"Failed to write SIMULATION_ENABLED to .env: {e}")


settings = Settings()
