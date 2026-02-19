"""Custom exceptions for algotik_tse package.

These exceptions provide more specific error types for different failure modes.
For backward compatibility, existing public functions still return None on error
and print error messages. These exceptions are available for advanced usage and
will be used internally for better error categorization.
"""


class AlgotikTSEError(Exception):
    """Base exception for all algotik_tse errors."""

    pass


class ConnectionError(AlgotikTSEError):
    """Raised when a connection to the data provider fails."""

    pass


class StockNotFoundError(AlgotikTSEError):
    """Raised when a stock symbol is not found."""

    pass


class InvalidParameterError(AlgotikTSEError):
    """Raised when an invalid parameter value is provided."""

    pass


class DataParsingError(AlgotikTSEError):
    """Raised when response data cannot be parsed correctly."""

    pass


class RateLimitError(AlgotikTSEError):
    """Raised when the server rate-limits or blocks requests."""

    pass
