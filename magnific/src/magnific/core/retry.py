"""Retry logic with error classification."""

import asyncio
import enum
import random
import time
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, Optional, TypeVar

from magnific.core.errors import (
    MagnificError,
    RateLimitError,
    RetryExhaustedError,
    SafetyFilterError,
)

T = TypeVar("T")


class ErrorAction(enum.Enum):
    """Classification of error actions."""
    RETRY = "retry"
    FAIL_SCENE = "fail_scene"
    ABORT_JOB = "abort_job"


class ErrorClassifier:
    """
    Maps exceptions to specific architectural actions.
    
    Critical distinction:
    - RETRY: Transient errors (429, 503) -> Backoff and retry
    - FAIL_SCENE: Permanent but recoverable (safety filter) -> Skip scene, continue pipeline
    - ABORT_JOB: Unrecoverable (invalid API key) -> Halt everything
    
    This prevents wasting API quota retrying permanent failures.
    """
    
    @staticmethod
    def classify(error: Exception) -> ErrorAction:
        """Classify an exception into an action."""
        # Known Magnific errors
        if isinstance(error, SafetyFilterError):
            return ErrorAction.FAIL_SCENE
        
        if isinstance(error, RateLimitError):
            return ErrorAction.RETRY
        
        # Google API errors (if google-api-core installed)
        try:
            from google.api_core import exceptions as gcp_errors
            
            # TRANSIENT - Retry with backoff
            if isinstance(error, gcp_errors.ResourceExhausted):  # 429
                return ErrorAction.RETRY
            if isinstance(error, gcp_errors.ServiceUnavailable):  # 503
                return ErrorAction.RETRY
            if isinstance(error, gcp_errors.DeadlineExceeded):    # 504
                return ErrorAction.RETRY
            if isinstance(error, gcp_errors.InternalServerError): # 500
                return ErrorAction.RETRY
            
            # PERMANENT - Do not waste quota retrying
            if isinstance(error, gcp_errors.InvalidArgument):     # 400
                return ErrorAction.FAIL_SCENE
            
            if isinstance(error, gcp_errors.PermissionDenied):    # 403
                # Could be auth failure OR safety filter
                error_str = str(error).lower()
                if "safety" in error_str or "blocked" in error_str or "content" in error_str:
                    return ErrorAction.FAIL_SCENE
                return ErrorAction.ABORT_JOB
            
            if isinstance(error, gcp_errors.Unauthenticated):     # 401
                return ErrorAction.ABORT_JOB
            
        except ImportError:
            pass
        
        # HTTP errors via httpx
        if hasattr(error, "status_code"):
            status = error.status_code
            if status == 429:
                return ErrorAction.RETRY
            if status in (500, 502, 503, 504):
                return ErrorAction.RETRY
            if status in (400, 403):
                return ErrorAction.FAIL_SCENE
            if status in (401, 403):
                return ErrorAction.ABORT_JOB
        
        # Default: Fail closed. Unknown errors not retried.
        return ErrorAction.FAIL_SCENE
    
    @staticmethod
    def get_retry_after(error: Exception) -> Optional[float]:
        """Extract Retry-After header value if present."""
        if hasattr(error, "retry_after"):
            return error.retry_after
        if hasattr(error, "response") and hasattr(error.response, "headers"):
            header = error.response.headers.get("Retry-After")
            if header:
                try:
                    return float(header)
                except ValueError:
                    pass
        return None


@dataclass
class RetryConfig:
    """Retry policy configuration."""
    max_attempts: int = 5
    base_delay_seconds: float = 2.0
    max_delay_seconds: float = 60.0
    backoff_multiplier: float = 2.0
    jitter: bool = True
    retryable_actions: set[ErrorAction] = field(
        default_factory=lambda: {ErrorAction.RETRY}
    )
    
    def calculate_delay(self, attempt: int, error: Optional[Exception] = None) -> float:
        """
        Calculate delay with exponential backoff and jitter.
        
        Formula: base * multiplier^attempt, capped at max
        With jitter: random factor 0.5-1.0
        """
        base = self.base_delay_seconds * (self.backoff_multiplier ** (attempt - 1))
        delay = min(base, self.max_delay_seconds)
        
        if self.jitter:
            delay = delay * (0.5 + random.random() * 0.5)
        
        # Respect Retry-After header if present
        if error:
            retry_after = ErrorClassifier.get_retry_after(error)
            if retry_after:
                delay = max(delay, retry_after)
        
        return delay


class RetryHandler:
    """
    Async retry handler with exponential backoff.
    
    Uses tenacity-like patterns but custom for our error classification.
    """
    
    def __init__(self, config: RetryConfig):
        self.config = config
    
    async def execute(
        self,
        fn: Callable[[], Awaitable[T]],
        error_classifier: Optional[Callable[[Exception], ErrorAction]] = None,
    ) -> T:
        """
        Execute async function with retry logic.
        
        Args:
            fn: Async function to execute
            error_classifier: Optional custom classifier
            
        Returns:
            Result of successful execution
            
        Raises:
            RetryExhaustedError: Max attempts exhausted
            MagnificError: Non-retryable error
        """
        classifier = error_classifier or ErrorClassifier.classify
        last_error: Optional[Exception] = None
        total_delay = 0.0
        
        for attempt in range(1, self.config.max_attempts + 1):
            try:
                return await fn()
            except Exception as e:
                action = classifier(e)
                last_error = e
                
                # Non-retryable: raise immediately
                if action not in self.config.retryable_actions:
                    raise
                
                # Exhausted attempts
                remaining = self.config.max_attempts - attempt
                if remaining == 0:
                    raise RetryExhaustedError(e, attempt, total_delay)
                
                # Calculate and apply delay
                delay = self.config.calculate_delay(attempt, e)
                await asyncio.sleep(delay)
                total_delay += delay
        
        # Should not reach here
        raise RetryExhaustedError(last_error or Exception("Unknown"), self.config.max_attempts, total_delay)
    
    def wrap(
        self,
        fn: Callable[..., Awaitable[T]],
        error_classifier: Optional[Callable[[Exception], ErrorAction]] = None,
    ) -> Callable[..., Awaitable[T]]:
        """Wrap a function with retry logic."""
        async def wrapped(*args: Any, **kwargs: Any) -> T:
            return await self.execute(lambda: fn(*args, **kwargs), error_classifier)
        return wrapped