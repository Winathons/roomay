"""Production ASGI entry point. Refuses to start without explicit configuration."""
from .app import create_app
from .config import Settings
from .db import make_database
from .hotel_data import UnavailableHotelSnapshotReader

settings = Settings.from_env().validate()
engine, SessionLocal = make_database(settings.database_url)
reader = UnavailableHotelSnapshotReader()
app = create_app(session_factory=SessionLocal, hotel_reader=reader, settings=settings)
