"""Reusable decorators for the interview-coach backend.

Demonstrates:
  - Decorator factory (functions returning decorators)
  - Closure (inner function capturing outer variables)
  - functools.wraps for transparent wrapping
  - Keyword-only arguments in decorator factories
  - Generic typing with TypeVar + ParamSpec
  - Global module-level logger (namespace)
"""
from __future__ import annotations

import functools
import time
import logging
from typing import Any, Callable, TypeVar

# ── Module-level (global namespace) logger ────────────────────────────────────
_logger = logging.getLogger(__name__)

F = TypeVar("F", bound=Callable[..., Any])


# ─────────────────────────────────────────────────────────────────────────────
# 1. validate_score — clamps a float return value to [lo, hi]
#    Demonstrates: closure (captures lo, hi), decorator factory
# ─────────────────────────────────────────────────────────────────────────────
def validate_score(*, lo: float = 0.0, hi: float = 1.0) -> Callable[[F], F]:
    """Decorator factory.  Clamps the float return of the wrapped function.

    Keyword-only args: lo, hi.

    Example
    -------
    @validate_score(lo=0.0, hi=1.0)
    def my_metric(...) -> float: ...
    """
    def decorator(fn: F) -> F:
        @functools.wraps(fn)           # preserves __name__, __doc__, etc.
        def wrapper(*args, **kwargs):
            # local variable — distinct from any outer scope
            result = fn(*args, **kwargs)
            if result is None:
                return None            # propagate None sentinel unchanged
            return float(max(lo, min(hi, result)))   # closure: lo, hi captured
        return wrapper  # type: ignore[return-value]
    return decorator


# ─────────────────────────────────────────────────────────────────────────────
# 2. log_call — logs entry / exit and elapsed time
#    Demonstrates: closure (captures level, logger), functools.wraps
# ─────────────────────────────────────────────────────────────────────────────
def log_call(*, level: int = logging.DEBUG) -> Callable[[F], F]:
    """Decorator factory — logs call entry, exit, and elapsed ms.

    Keyword-only arg: level (logging level constant).
    """
    def decorator(fn: F) -> F:
        @functools.wraps(fn)
        def wrapper(*args, **kwargs):
            _logger.log(level, "→ %s called", fn.__qualname__)   # closure: fn, level
            t0 = time.perf_counter()
            try:
                result = fn(*args, **kwargs)
                elapsed = (time.perf_counter() - t0) * 1000
                _logger.log(level, "← %s returned in %.1f ms", fn.__qualname__, elapsed)
                return result
            except Exception as exc:
                _logger.log(logging.ERROR, "✗ %s raised %s", fn.__qualname__, exc)
                raise
        return wrapper  # type: ignore[return-value]
    return decorator


# ─────────────────────────────────────────────────────────────────────────────
# 3. retry — retries on exception up to max_attempts times
#    Demonstrates: closure (captures max_attempts, delay, exceptions), factory
# ─────────────────────────────────────────────────────────────────────────────
def retry(
    *,
    max_attempts: int = 3,
    delay: float = 0.1,
    exceptions: tuple[type[Exception], ...] = (Exception,),
) -> Callable[[F], F]:
    """Retry a function up to max_attempts times with a fixed delay (seconds).

    Keyword-only args: max_attempts, delay, exceptions.
    """
    def decorator(fn: F) -> F:
        @functools.wraps(fn)
        def wrapper(*args, **kwargs):
            # Local variable tracking attempt count (closure captures fn, max_attempts, ...)
            last_exc: Exception | None = None
            for attempt in range(1, max_attempts + 1):
                try:
                    return fn(*args, **kwargs)
                except exceptions as exc:      # noqa: BLE001
                    last_exc = exc
                    if attempt < max_attempts:
                        _logger.warning(
                            "retry %d/%d for %s after: %s",
                            attempt, max_attempts, fn.__qualname__, exc,
                        )
                        time.sleep(delay)
            raise last_exc  # type: ignore[misc]
        return wrapper  # type: ignore[return-value]
    return decorator


# ─────────────────────────────────────────────────────────────────────────────
# 4. memoize — simple LRU-style cache for pure functions
#    Demonstrates: closure (captures cache dict), decorator without factory form
# ─────────────────────────────────────────────────────────────────────────────
def memoize(fn: F) -> F:
    """Cache calls by positional args (args must be hashable).

    Single-argument form (no factory), applied directly as @memoize.
    """
    cache: dict[tuple, Any] = {}          # closure variable

    @functools.wraps(fn)
    def wrapper(*args):
        if args not in cache:
            cache[args] = fn(*args)       # closure: cache captured
        return cache[args]

    wrapper.cache = cache                  # type: ignore[attr-defined]  expose for inspection
    return wrapper  # type: ignore[return-value]
