import os
from functools import lru_cache

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from .models import Base

DEFAULT_URL = "sqlite:///./acp.db"


@lru_cache(maxsize=1)
def get_engine():
    url = os.environ.get("ACP_DATABASE_URL", DEFAULT_URL)
    connect_args = {"check_same_thread": False} if url.startswith("sqlite") else {}
    return create_engine(url, connect_args=connect_args)


@lru_cache(maxsize=1)
def get_session_factory():
    return sessionmaker(bind=get_engine(), expire_on_commit=False)


def init_db() -> None:
    """Crée les tables manquantes (MVP ; une migration Alembic viendra ensuite)."""
    Base.metadata.create_all(get_engine())
