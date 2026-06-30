"""Decorators — cross-cutting concerns for services and API handlers."""

import functools
import time
from typing import Any, Callable

from loguru import logger


def timed(func: Callable) -> Callable:
    """Log execution time of a callable."""

    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        start = time.perf_counter()
        result = func(*args, **kwargs)
        elapsed_ms = (time.perf_counter() - start) * 1000
        logger.debug(f"{func.__name__} finished in {elapsed_ms:.2f} ms")
        return result

    return wrapper


def requires_mode(*allowed_modes: str) -> Callable:
    """Only run when the recognizer is in one of the allowed modes."""

    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(self, *args, **kwargs):
            mode = getattr(self, "mode", "mock")
            if mode not in allowed_modes:
                raise RuntimeError(
                    f"{func.__name__} requires mode {allowed_modes}, got '{mode}'"
                )
            return func(self, *args, **kwargs)

        return wrapper

    return decorator


def log_inference(func: Callable) -> Callable:
    """Log prediction outcomes from recognizer methods."""

    @functools.wraps(func)
    def wrapper(*args, **kwargs) -> Any:
        result = func(*args, **kwargs)
        label = getattr(result, "label", None)
        if label is None and isinstance(result, dict):
            label = result.get("label")
        if label is not None:
            confidence = getattr(result, "confidence", None)
            if confidence is None and isinstance(result, dict):
                confidence = result.get("confidence", 0.0)
            source = getattr(result, "source", None)
            if source is None and isinstance(result, dict):
                source = result.get("source", "unknown")
            logger.info(
                "Prediction: {label} ({confidence:.2f}) via {source}",
                label=label,
                confidence=confidence or 0.0,
                source=source or "unknown",
            )
        return result

    return wrapper