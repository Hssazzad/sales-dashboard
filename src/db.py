from pathlib import Path
import os
from urllib.parse import quote_plus

from dotenv import load_dotenv
import streamlit as st
from sqlalchemy import create_engine
from sqlalchemy.engine import Engine

PROJECT_ROOT = Path(__file__).resolve().parents[1]
load_dotenv(PROJECT_ROOT / ".env")


def _setting(name: str) -> str | None:
    """Read deployment secrets first, then fall back to local environment."""
    try:
        value = st.secrets.get(name)
    except (FileNotFoundError, KeyError):
        value = None
    if value is not None:
        return str(value)
    return os.getenv(name)


def get_engine() -> Engine:
    required = ("DB_HOST", "DB_PORT", "DB_USER", "DB_PASSWORD", "DB_NAME")
    settings = {key: _setting(key) for key in required}
    missing = [key for key, value in settings.items() if value is None]
    if missing:
        raise RuntimeError(
            "Missing required database configuration: "
            f"{', '.join(missing)}. Set all five DB_* keys in "
            "Streamlit Cloud Secrets, or in .env for local development."
        )

    user = quote_plus(settings["DB_USER"])
    password = quote_plus(settings["DB_PASSWORD"])
    host = settings["DB_HOST"]
    port = settings["DB_PORT"]
    database = quote_plus(settings["DB_NAME"])

    url = (
        f"mysql+pymysql://{user}:{password}@{host}:{port}/{database}"
        "?charset=utf8mb4"
    )
    ssl_enabled = _setting("DB_SSL")
    if ssl_enabled is None:
        ssl_enabled = str(host).lower() not in {"127.0.0.1", "localhost"}
    connect_args = {}
    if str(ssl_enabled).lower() in {"1", "true", "yes", "on"}:
        ca_path = _setting("DB_SSL_CA") or "certs/isrgrootx1.pem"
        ca_file = Path(ca_path)
        if not ca_file.is_absolute():
            ca_file = PROJECT_ROOT / ca_file
        if not ca_file.is_file():
            raise RuntimeError(f"Database SSL certificate not found: {ca_file}")
        connect_args["ssl"] = {
            "ca": str(ca_file),
            "check_hostname": True,
        }
    return create_engine(url, connect_args=connect_args, pool_pre_ping=True)
