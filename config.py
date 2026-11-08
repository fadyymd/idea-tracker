"""Application configuration.

Values are read from environment variables so that the same code runs in
development (SQLite) and production (PostgreSQL) without modification.
"""
import os
import secrets

BASE_DIR = os.path.abspath(os.path.dirname(__file__))
INSTANCE_DIR = os.path.join(BASE_DIR, "instance")


def _database_url() -> str:
    url = os.environ.get("DATABASE_URL")
    if not url:
        return "sqlite:///" + os.path.join(INSTANCE_DIR, "idea_tracker.db")
    # Heroku / Render still hand out "postgres://" which SQLAlchemy rejects.
    if url.startswith("postgres://"):
        url = url.replace("postgres://", "postgresql://", 1)
    return url


def _secret_key() -> str:
    """Use $SECRET_KEY; otherwise generate a random key once and keep it in instance/.

    This avoids the classic "hard-coded dev secret" vulnerability while keeping
    sessions valid across restarts when no environment variable is configured.
    """
    key = os.environ.get("SECRET_KEY")
    if key:
        return key
    path = os.path.join(INSTANCE_DIR, ".secret_key")
    try:
        os.makedirs(INSTANCE_DIR, exist_ok=True)
        try:
            fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        except FileExistsError:  # another worker won the race (or a previous run created it)
            with open(path, encoding="utf-8") as fh:
                existing = fh.read().strip()
            if existing:
                return existing
            return secrets.token_hex(32)
        key = secrets.token_hex(32)
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(key)
        return key
    except OSError:  # read-only file system etc. -> ephemeral key
        return secrets.token_hex(32)


class Config:
    SECRET_KEY = _secret_key()
    SQLALCHEMY_DATABASE_URI = _database_url()
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_ENGINE_OPTIONS = {"pool_pre_ping": True}

    IDEAS_PER_PAGE = 10
    MAX_COMMENT_LENGTH = 2000

    # Brute-force protection for the login form (per client IP + identifier).
    LOGIN_MAX_ATTEMPTS = 5
    LOGIN_WINDOW_SECONDS = 15 * 60

    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    SESSION_COOKIE_SECURE = os.environ.get("SESSION_COOKIE_SECURE", "0") == "1"
    REMEMBER_COOKIE_HTTPONLY = True
    REMEMBER_COOKIE_SAMESITE = "Lax"
    REMEMBER_COOKIE_SECURE = SESSION_COOKIE_SECURE

    WTF_CSRF_TIME_LIMIT = 60 * 60 * 8  # 8 hours

    # Set to 1 behind a reverse proxy (Render, Heroku, nginx) so client IPs / HTTPS are detected correctly.
    TRUST_PROXY = os.environ.get("TRUST_PROXY", "0") == "1"


class TestConfig(Config):
    TESTING = True
    SECRET_KEY = "test-secret"
    SQLALCHEMY_DATABASE_URI = "sqlite://"  # in-memory
    SQLALCHEMY_ENGINE_OPTIONS = {}
    WTF_CSRF_ENABLED = False
    IDEAS_PER_PAGE = 8
