"""Explicit exception hierarchy for Magnific pipeline."""

class MagnificError(Exception):
    """Base exception for all Magnific errors."""
    pass


class SecurityViolationError(MagnificError):
    """CWE-22: Path traversal attempt blocked."""
    pass


class PreFlightError(MagnificError):
    """Pre-flight validation failed (disk, memory, input validation)."""
    pass


class ConfigValidationError(MagnificError):
    """Configuration schema validation failed."""
    pass


class ManifestValidationError(MagnificError):
    """Manifest schema validation failed."""
    pass


class StageNotFoundError(MagnificError):
    """Required manifest for stage not found."""
    pass


class ProviderError(MagnificError):
    """External provider API error."""
    def __init__(self, message: str, provider: str, retryable: bool = False):
        super().__init__(message)
        self.provider = provider
        self.retryable = retryable


class SafetyFilterError(ProviderError):
    """Content safety filter blocked the request (PERMANENT, no retry)."""
    def __init__(self, message: str, provider: str = "google"):
        super().__init__(message, provider, retryable=False)


class RateLimitError(ProviderError):
    """API rate limit exceeded (TRANSIENT, retry with backoff)."""
    def __init__(self, message: str, provider: str = "google", retry_after: float | None = None):
        super().__init__(message, provider, retryable=True)
        self.retry_after = retry_after


class RetryExhaustedError(MagnificError):
    """Max retry attempts exhausted."""
    def __init__(self, last_error: Exception, attempts: int, total_delay: float):
        super().__init__(f"Retry exhausted after {attempts} attempts ({total_delay:.1f}s)")
        self.last_error = last_error
        self.attempts = attempts
        self.total_delay = total_delay


class DiskFullError(MagnificError):
    """Insufficient disk space."""
    pass


class InvalidApiKeyError(MagnificError):
    """API key missing or invalid."""
    pass


class BudgetExceededError(MagnificError):
    """Budget limit exceeded - prevents runaway costs."""
    pass