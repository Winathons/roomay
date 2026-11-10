"""Production ASGI entry point. Refuses to start without explicit configuration."""
from .app import create_app
from .config import Settings
from .db import make_database
from .workpeg_reader import WorkpegHotelReader

settings = Settings.from_env().validate()
engine, SessionLocal = make_database(settings.database_url)
reader = WorkpegHotelReader(api_base=settings.workpeg_api,
                            workpeg_pk=settings.workpeg_pk,
                            peg_id=settings.peg_id)
app = create_app(session_factory=SessionLocal, hotel_reader=reader, settings=settings)
