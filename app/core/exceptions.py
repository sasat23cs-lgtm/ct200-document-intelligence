"""Application-wide exception hierarchy.

Every domain error the API can raise inherits from AppError, which carries
an HTTP status code and a machine-readable `code` so the API layer can map
it to a consistent JSON error body without each router hand-rolling HTTPException
logic. This keeps error handling centralized (see app/api/errors.py).
"""


class AppError(Exception):
    status_code: int = 500
    code: str = "internal_error"

    def __init__(self, message: str):
        self.message = message
        super().__init__(message)


class NotFoundError(AppError):
    status_code = 404
    code = "not_found"


class ValidationFailedError(AppError):
    """Raised when a request is semantically invalid (not a schema/type error,
    which Pydantic already handles, but a business-rule violation)."""

    status_code = 422
    code = "validation_failed"


class ParserError(AppError):
    """Raised by the markdown parser when it encounters input it cannot
    structurally interpret with confidence. Fail loud, never guess."""

    status_code = 422
    code = "parser_error"


class LLMGenerationError(AppError):
    """Raised when the LLM provider fails or its output cannot be validated
    even after one retry."""

    status_code = 502
    code = "llm_generation_failed"
