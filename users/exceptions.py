"""Domain-specific exceptions used outside normal DRF validation."""


class EmailNotVerifiedForLogin(Exception):
    """Raised when credentials are valid but the user must verify email (client → Settings)."""

    pass
