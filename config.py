import os
from datetime import timedelta

from dotenv import load_dotenv
from sqlalchemy.engine import URL

BASE_DIR = os.path.abspath(os.path.dirname(__file__))
load_dotenv(os.path.join(BASE_DIR, ".env"))


def _bool(value, default=False):
    if value is None:
        return default
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def build_database_uri() -> str:
    explicit = os.environ.get("DATABASE_URL")
    if explicit:
        return explicit
    return URL.create(
        drivername="mysql+pymysql",
        username=os.environ.get("DB_USER", "root"),
        password=os.environ.get("DB_PASSWORD", ""),
        host=os.environ.get("DB_HOST", "127.0.0.1"),
        port=int(os.environ.get("DB_PORT", "3306")),
        database=os.environ.get("DB_NAME", "memospace"),
        query={"charset": "utf8mb4"},
    ).render_as_string(hide_password=False)


class Config:
    APP_ENV = os.environ.get("APP_ENV", "development").lower()
    IS_PRODUCTION = APP_ENV == "production"
    DEBUG = not IS_PRODUCTION

    SECRET_KEY = os.environ.get("SECRET_KEY")

    SQLALCHEMY_DATABASE_URI = build_database_uri()
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_ENGINE_OPTIONS = {"pool_pre_ping": True, "pool_recycle": 280}

    APP_TIMEZONE = os.environ.get("APP_TIMEZONE", "Asia/Jakarta")
    TRASH_RETENTION_DAYS = int(os.environ.get("TRASH_RETENTION_DAYS", "30"))
    AUTO_CREATE_TABLES = _bool(os.environ.get("AUTO_CREATE_TABLES"), True)

    SESSION_COOKIE_NAME = "memospace_session"
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    SESSION_COOKIE_SECURE = _bool(os.environ.get("SESSION_COOKIE_SECURE"), IS_PRODUCTION)
    PERMANENT_SESSION_LIFETIME = timedelta(days=365 * 5)
    SESSION_REFRESH_EACH_REQUEST = True

    WTF_CSRF_TIME_LIMIT = None  
    MAX_CONTENT_LENGTH = 1 * 1024 * 1024  

    NOTE_TITLE_MAX = 255
    NOTE_CONTENT_MAX = 100_000
    NAME_MAX = 100
    NOTES_PER_PAGE = 12


class TestConfig(Config):
    TESTING = True
    DEBUG = False
    SECRET_KEY = "test-secret-key-not-for-production"
    SQLALCHEMY_DATABASE_URI = "sqlite://"
    SQLALCHEMY_ENGINE_OPTIONS = {}
    WTF_CSRF_ENABLED = True
    SESSION_COOKIE_SECURE = False
    AUTO_CREATE_TABLES = True
