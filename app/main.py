from fastapi import FastAPI

from app.api.browse import router as browse_router
from app.api.errors import register_error_handlers
from app.api.ingestion import router as ingestion_router
from app.api.search import router as search_router
from app.api.selections import router as selections_router
from app.api.generation import router as generation_router
from app.api.testcases import router as testcases_router
from app.core.config import settings
from app.core.logging import configure_logging
from app.database.init_db import init_db

configure_logging()

app = FastAPI(
    title=settings.app_name,
    description=(
        "Turns the CardioTrack CT-200 manual into a browsable, versioned "
        "document tree and generates QA test cases from user-selected "
        "sections, with traceability and staleness detection across "
        "document re-ingestion."
    ),
    version="1.0.0",
)

register_error_handlers(app)


@app.on_event("startup")
def on_startup() -> None:
    init_db()


app.include_router(browse_router, prefix="/api/v1")
app.include_router(search_router, prefix="/api/v1")
app.include_router(ingestion_router, prefix="/api/v1")
app.include_router(selections_router, prefix="/api/v1")
app.include_router(generation_router, prefix="/api/v1")
app.include_router(testcases_router, prefix="/api/v1")


@app.get("/", tags=["meta"])
def root():
    return {"service": settings.app_name, "docs": "/docs"}
