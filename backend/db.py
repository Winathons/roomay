"""SQLAlchemy engine and request-scoped sessions."""
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker


def make_database(url):
    if not isinstance(url, str) or not url:
        raise RuntimeError("database_configuration_missing")
    engine = create_engine(url, pool_pre_ping=True, future=True)
    return engine, sessionmaker(bind=engine, expire_on_commit=False, future=True)
