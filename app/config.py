import os
class Config:
    BASE_DIR = os.path.abspath(os.path.dirname(os.path.dirname(__file__)))
    SECRET_KEY = os.environ.get("SECRET_KEY", "sms-group02-secret-key-2026")
    DATABASE_PATH = os.environ.get(
        "DATABASE_PATH", os.path.join(BASE_DIR, "instance", "sms_group02.db")
    )
    MAX_FAILED_LOGIN_ATTEMPTS = 5
    LOCK_DURATION_MINUTES = 15
    RESET_TOKEN_EXPIRY_MINUTES = 15
    PER_PAGE = 10
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
class TestConfig(Config):
    TESTING = True
    SECRET_KEY = "test-secret-key"
