"""Common error definitions and response builders."""

from typing import Dict, Any, Optional


class GatewayError(Exception):
    """Base exception for gateway errors."""
    
    def __init__(self, code: str, message: str, status_code: int = 500, details: Optional[Dict[str, Any]] = None):
        self.code = code
        self.message = message
        self.status_code = status_code
        self.details = details or {}
        super().__init__(message)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert error to API response format."""
        return {
            'error': {
                'code': self.code,
                'message': self.message,
                'details': self.details
            }
        }


class AuthenticationError(GatewayError):
    """Authentication-related errors (401)."""
    
    def __init__(self, code: str, message: str, details: Optional[Dict[str, Any]] = None):
        super().__init__(code, message, 401, details)


class AuthorizationError(GatewayError):
    """Authorization-related errors (403)."""
    
    def __init__(self, code: str, message: str, details: Optional[Dict[str, Any]] = None):
        super().__init__(code, message, 403, details)


class NotFoundError(GatewayError):
    """Resource not found errors (404)."""
    
    def __init__(self, code: str, message: str, details: Optional[Dict[str, Any]] = None):
        super().__init__(code, message, 404, details)


class BadRequestError(GatewayError):
    """Bad request errors (400)."""
    
    def __init__(self, code: str, message: str, details: Optional[Dict[str, Any]] = None):
        super().__init__(code, message, 400, details)


class BackendError(GatewayError):
    """Backend communication errors (502)."""
    
    def __init__(self, code: str, message: str, details: Optional[Dict[str, Any]] = None):
        super().__init__(code, message, 502, details)


class TimeoutError(GatewayError):
    """Timeout errors (504)."""
    
    def __init__(self, code: str, message: str, details: Optional[Dict[str, Any]] = None):
        super().__init__(code, message, 504, details)


# Common error codes
MISSING_AUTH_HEADER = "MISSING_AUTH_HEADER"
INVALID_JWT_SIGNATURE = "INVALID_JWT_SIGNATURE"
EXPIRED_JWT = "EXPIRED_JWT"
INVALID_JWT_ISSUER = "INVALID_JWT_ISSUER"
PERMISSION_DENIED = "PERMISSION_DENIED"
ADMIN_PERMISSION_REQUIRED = "ADMIN_PERMISSION_REQUIRED"
AGENT_NOT_FOUND = "AGENT_NOT_FOUND"
INVALID_PATH_FORMAT = "INVALID_PATH_FORMAT"
BACKEND_UNREACHABLE = "BACKEND_UNREACHABLE"
OAUTH_ERROR = "OAUTH_ERROR"
STREAM_IDLE_TIMEOUT = "STREAM_IDLE_TIMEOUT"
