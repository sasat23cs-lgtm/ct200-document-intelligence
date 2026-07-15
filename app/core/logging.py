import logging
import sys

from app.core.config import settings


def configure_logging() -> None:
    """Configure structured, single-line logging for the whole app.

    Kept deliberately simple (stdlib logging, no external log framework) —
    this is a take-home API, not a service that needs log aggregation tooling.
    """
    logging.basicConfig(
        level=getattr(logging, settings.log_level.upper(), logging.INFO),
        format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        stream=sys.stdout,
    )


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)
