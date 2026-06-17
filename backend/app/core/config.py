"""
Application configuration using Pydantic Settings
"""
from pathlib import Path
from typing import List
from pydantic_settings import BaseSettings, SettingsConfigDict


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

    # --- KTM-2000 Integration Settings ---
    USE_KTM_API: bool = False
    KTM_BACKEND_URL: str = "http://localhost:8010" # Default for local dev, can be set via env

    # --- OPC UA Configuration ---
    OPCUA_ENABLED: bool = True # Master switch to enable/disable OPC UA service
    OPCUA_ENDPOINT: str = "opc.tcp://172.17.11.131:4840/"
    OPCUA_SIM_ENDPOINT: str = "opc.tcp://127.0.0.1:4840/freeopcua/server/" # Simulator endpoint
    OPCUA_POLL_INTERVAL: int = 5  # Seconds between polls for real server
    OPCUA_SIM_POLL_INTERVAL: int = 1  # Seconds between polls for simulation

    # Excel file paths
    EXCEL_REAL_FILE_PATH: str = "//ktm-disk/Оператор/Учет КПЗ 2026.xlsm"
    EXCEL_TEST_FILE_PATH: str = "../testdata/Учет КПЗ 2026.xlsm"
    
    # Static files
    STATIC_DIR: str = "../static"  # Relative to backend folder
    IMAGES_DIR: str = "../static/images"
    
    # Photo upload
    MAX_UPLOAD_SIZE: int = 10 * 1024 * 1024  # 10MB
    THUMBNAIL_SIZE: tuple = (200, 200)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Load from json file
        try:
            import json
            static_path = Path(self.STATIC_DIR)
            settings_file = static_path / "app_settings.json"
            if settings_file.exists():
                with open(settings_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    if "use_ktm_api" in data:
                        self.USE_KTM_API = bool(data["use_ktm_api"])
        except Exception:
            pass
    
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

    def update_app_settings(self, use_ktm_api: bool) -> None:
        """Saves settings to app_settings.json and updates in-memory config"""
        self.USE_KTM_API = use_ktm_api
        try:
            import json
            static_dir = Path(self.STATIC_DIR)
            static_dir.mkdir(parents=True, exist_ok=True)
            settings_file = static_dir / "app_settings.json"
            
            data = {}
            if settings_file.exists():
                with open(settings_file, "r", encoding="utf-8") as f:
                    try:
                        data = json.load(f)
                    except Exception:
                        pass
                        
            data["use_ktm_api"] = use_ktm_api
            
            with open(settings_file, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            import logging
            logging.getLogger(__name__).error(f"Failed to save app_settings.json: {e}")

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
