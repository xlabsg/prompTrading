"""Custom exceptions for OKX SDK."""


class OKXError(Exception):
    """Base exception for OKX SDK errors."""
    pass


class OKXAuthError(OKXError):
    """Authentication error (invalid API credentials)."""
    pass


class OKXAPIError(OKXError):
    """API request error from OKX."""
    
    def __init__(self, message: str, code: str = "", data: dict = None):
        super().__init__(message)
        self.code = code
        self.data = data or {}
