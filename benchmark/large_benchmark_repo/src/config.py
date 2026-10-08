"""Core system configuration."""
import os

class AppConfig:
    ENV: str = os.getenv("APP_ENV", "production")
    DEBUG: bool = False
    PORT: int = 8080
    SECRET_KEY: str = os.getenv("SECRET_KEY", "super-secret-key")
    DB_POOL_SIZE: int = 20
