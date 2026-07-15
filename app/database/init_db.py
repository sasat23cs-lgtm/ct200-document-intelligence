from app.database.session import Base, engine
import app.models  # noqa: F401 — registers all models on Base.metadata


def init_db() -> None:
    Base.metadata.create_all(bind=engine)
