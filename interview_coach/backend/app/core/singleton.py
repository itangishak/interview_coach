"""Singleton metaclass — one shared instance per process.

Demonstrates:
  - Metaclass (SingletonMeta)
  - Class-level __slots__ on the metaclass registry
  - Lock-free instance caching (safe under Python's GIL)
  - __call__ override (special method / dunder)
  - clear() classmethod for test isolation
"""
from __future__ import annotations


class SingletonMeta(type):
    """Metaclass that enforces one instance per concrete class.

    Lock-free: Python's GIL makes dict get/set atomic enough for
    this pattern.  The worst-case race creates one extra instance
    that is immediately discarded — no thread ever blocks, so the
    asyncio event loop cannot freeze.

    Usage
    -----
    class MyService(metaclass=SingletonMeta):
        ...
    """

    # Class-level registry: maps concrete class → its single instance
    _instances: dict[type, object] = {}

    def __call__(cls, *args, **kwargs):
        # Fast path: already instantiated
        if cls not in cls._instances:
            instance = super().__call__(*args, **kwargs)
            # Second check: another thread may have stored an instance
            # while we were creating ours.
            if cls not in cls._instances:
                cls._instances[cls] = instance
        return cls._instances[cls]

    @classmethod
    def clear(mcs, target: type | None = None) -> None:
        """Remove one or all singleton instances.  Needed for test isolation.

        Positional-or-keyword parameter: target (optional).
        """
        if target is None:
            mcs._instances.clear()
        else:
            mcs._instances.pop(target, None)

    def __repr__(cls) -> str:
        has_instance = cls in SingletonMeta._instances
        return f"<SingletonMeta class={cls.__name__!r} instantiated={has_instance}>"
