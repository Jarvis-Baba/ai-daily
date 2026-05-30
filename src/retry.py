import logging
import time
from typing import Any, Callable

logger = logging.getLogger(__name__)


def retry_call(
    fn: Callable,
    *args,
    max_attempts: int = 3,
    backoff_seconds: float = 1.0,
    retryable_exceptions: tuple = (Exception,),
    logger: logging.Logger | None = None,
    **kwargs,
) -> Any:
    """Call fn(*args, **kwargs) with exponential backoff retry.

    On retryable exception: wait backoff_seconds * (2 ** (attempt-1)), retry.
    On final attempt failure: re-raise the last exception.
    """
    log = logger or logging.getLogger(__name__)
    last_exception: Exception | None = None

    for attempt in range(max_attempts):
        try:
            return fn(*args, **kwargs)
        except retryable_exceptions as e:
            last_exception = e
            if attempt + 1 < max_attempts:
                wait = backoff_seconds * (2 ** attempt)
                log.warning(
                    "Retry attempt %d/%d after error: %s. Waiting %.1fs.",
                    attempt + 1,
                    max_attempts,
                    e,
                    wait,
                )
                time.sleep(wait)
            else:
                log.error(
                    "All %d retry attempts exhausted. Last error: %s",
                    max_attempts,
                    e,
                )

    raise last_exception  # type: ignore[misc]
