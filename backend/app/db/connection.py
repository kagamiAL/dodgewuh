"""Coordinator-only database configuration and connection lifecycle."""
import os
from pathlib import Path
from sqlalchemy import URL, create_engine
from sqlalchemy.orm import sessionmaker


def database_url():
    """Build a driver URL, preferring the mounted production password file."""
    secret = os.getenv("DB_PASSWORD_FILE")
    # Strip file line endings only: spaces can be intentional password characters.
    password = Path(secret).read_text().rstrip("\r\n") if secret else os.environ["PGPASSWORD"]
    if not password:
        raise ValueError("Database password must not be empty")
    # URL.create handles special characters without manual password escaping.
    return URL.create("postgresql+psycopg", username=os.getenv("PGUSER", "dodgewuh"),
                      password=password, host=os.getenv("PGHOST", "localhost"),
                      port=int(os.getenv("PGPORT", "5432")), database=os.getenv("PGDATABASE", "dodgewuh"))


def make_engine():
    """Create a bounded connection pool; discard stale connections before reuse."""
    return create_engine(database_url(), pool_pre_ping=True, pool_size=5, max_overflow=5,
                         connect_args={"connect_timeout": 5}, hide_parameters=True)


def sessions(engine):
    """Create short-lived transaction sessions whose results remain readable after commit."""
    return sessionmaker(engine, expire_on_commit=False)
