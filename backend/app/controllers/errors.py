"""
Domain-level exceptions raised by controllers. These carry no HTTP
knowledge (no status codes) - the views layer is responsible for
translating them into HTTPException responses.
"""


class DomainError(Exception):
    """Base class for expected, user-facing business errors."""


class DuplicateEmailError(DomainError):
    def __init__(self) -> None:
        super().__init__("An account with this email already exists")


class InvalidCredentialsError(DomainError):
    def __init__(self) -> None:
        super().__init__("Invalid email or password")


class InvalidRefreshTokenError(DomainError):
    def __init__(self) -> None:
        super().__init__("Refresh token is invalid, expired, or revoked")


class NotFoundError(DomainError):
    def __init__(self, message: str = "Resource not found") -> None:
        super().__init__(message)


class ForbiddenError(DomainError):
    def __init__(self, message: str = "You do not have access to this resource") -> None:
        super().__init__(message)
