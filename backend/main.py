"""Dormant standalone prototype ASGI entry point — NOT a Workpeg write path.

Neither importing this module nor configuring database credentials should
enable an operational guest service. Explicit local-only opt-in is required,
and the hotel-data adapter still returns 503 until vendor approval.
"""
from .config import Settings, require_experimental_backend_opt_in

# Run before importing the app or constructing a database connection.
require_experimental_backend_opt_in()

from .app import create_app  # noqa: E402
from .db import make_database  # noqa: E402
from .hotel_data import UnavailableHotelSnapshotReader  # noqa: E402

settings = Settings.from_env().validate()
engine, SessionLocal = make_database(settings.database_url)
reader = UnavailableHotelSnapshotReader()
app = create_app(session_factory=SessionLocal, hotel_reader=reader, settings=settings)
