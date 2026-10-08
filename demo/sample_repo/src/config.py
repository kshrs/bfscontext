"""
Configuration settings for billing service.
"""

import os


class Config:
    STRIPE_API_KEY: str = os.getenv("STRIPE_API_KEY", "sk_test_demo123456789")
    DATABASE_URL: str = os.getenv("DATABASE_URL", "sqlite:///test.db")
    MAX_RETRIES: int = 3
    CURRENCY: str = "USD"
