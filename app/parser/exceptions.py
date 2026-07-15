from app.core.exceptions import ParserError


class MalformedTableError(ParserError):
    """A pipe-table block had rows with an inconsistent column count."""


class EmptyDocumentError(ParserError):
    """The input contained no top-level (H1) heading at all."""


class MalformedHeadingError(ParserError):
    """A heading line matched the ATX pattern but produced an invalid level."""
