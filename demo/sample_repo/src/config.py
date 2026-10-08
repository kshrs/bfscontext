"""
Configuration settings and environment variable bindings for billing service.
"""

from __future__ import annotations

import os
from typing import Dict, Optional


class Config:
    """Core configuration for payment gateways and database connections."""
    STRIPE_API_KEY: str = os.getenv("STRIPE_API_KEY", "sk_test_demo123456789")
    DATABASE_URL: str = os.getenv("DATABASE_URL", "sqlite:///test.db")
    MAX_RETRIES: int = 3
    CURRENCY: str = "USD"
    TIMEOUT_SECONDS: int = 30
    ENABLE_AUDIT_LOG: bool = True
    APP_ENV: str = os.getenv("APP_ENV", "development")

    @classmethod
    def get_gateway_credentials(cls) -> Dict[str, str]:
        """Returns API credentials dictionary."""
        return {
            "api_key": cls.STRIPE_API_KEY,
            "currency": cls.CURRENCY,
            "env": cls.APP_ENV,
        }

    @classmethod
    def is_production(cls) -> bool:
        """Determines if the running environment is production."""
        return cls.APP_ENV.lower() == "production"

    @classmethod
    def get_timeout_ms(cls) -> int:
        """Returns connection timeout in milliseconds."""
        return cls.TIMEOUT_SECONDS * 1000


class DatabaseConfig:
    """Database connection pool configuration."""
    POOL_SIZE: int = 10
    MAX_OVERFLOW: int = 20
    POOL_TIMEOUT: int = 30
    POOL_RECYCLE_SECONDS: int = 1800
    ECHO_SQL: bool = False

    @classmethod
    def to_dict(cls) -> Dict[str, Any]:
        return {
            "pool_size": cls.POOL_SIZE,
            "max_overflow": cls.MAX_OVERFLOW,
            "pool_timeout": cls.POOL_TIMEOUT,
            "recycle": cls.POOL_RECYCLE_SECONDS,
        }


class NotificationConfig:
    """Outbound alerting and notification endpoints."""
    SLACK_WEBHOOK_URL: Optional[str] = os.getenv("SLACK_WEBHOOK_URL")
    ALERT_ON_FAILURE: bool = True
    MAX_ALERTS_PER_HOUR: int = 50
    ADMIN_EMAIL: str = os.getenv("ADMIN_EMAIL", "ops@company.internal")


class RateLimitConfig:
    """API rate limiting policies for billing transactions."""
    MAX_REQUESTS_PER_MINUTE: int = 120
    BURST_MULTIPLIER: int = 2
    BLOCK_DURATION_SECONDS: int = 300
    RATE_LIMIT_STORAGE_KEY: str = "rate_limit:billing"
