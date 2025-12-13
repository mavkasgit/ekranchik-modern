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
    
    # Excel file path
    EXCEL_FILE_PATH: str = ""
    
    # FTP Configuration (Omron PLC)
    FTP_HOST: str = "172.17.11.194"
    FTP_PORT: int = 21
    FTP_USER: str = "omron"
    FTP_PASSWORD: str = "12345678"
    FTP_BASE_PATH: str = "/MEMCARD1/messages/"
    FTP_POLL_INTERVAL: int = 60
    
    # Telegram Bot
    TELEGRAM_TOKEN: str = ""
    BOT_PASSWORD: str = "1122"
    
    # Static files
    STATIC_DIR: str = "../static"  # Relative to backend folder
    IMAGES_DIR: str = "../static/images"
    
    # Photo upload
    MAX_UPLOAD_SIZE: int = 10 * 1024 * 1024  # 10MB
    THUMBNAIL_SIZE: tuple = (200, 200)
    
    @property
    def excel_path(self) -> Path | None:
        """Get Excel file path as Path object"""
        if self.EXCEL_FILE_PATH:
            return Path(self.EXCEL_FILE_PATH)
        return None
    
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


settings = Settings()
