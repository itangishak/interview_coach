"""Singleton metaclass — thread-safe, one shared instance per process.

Demonstrates:
  - Metaclass (SingletonMeta)
  - Class-level __slots__ on the metaclass registry
  - Thread-safety via threading.Lock (global variable used intentionally)
  - __call__ override (special method / dunder)
  - clear() classmethod for test isolation
"""
from __future__ import annotations

import threading

# ── Module-level (global) lock — shared across all Singleton subclasses ───────
_SINGLETON_LOCK: threading.Lock = threading.Lock()


class SingletonMeta(type):
    """Metaclass that enforces one instance per concrete class.

    Usage
    -----
    class MyService(metaclass=SingletonMeta):
        ...
    """

    # Class-level registry: maps concrete class → its single instance
    _instances: dict[type, object] = {}

    def __call__(cls, *args, **kwargs):
        # Double-checked locking: cheap read first, lock only when needed
        if cls not in cls._instances:
            with _SINGLETON_LOCK:
                if cls not in cls._instances:                     # second check inside lock
                    instance = super().__call__(*args, **kwargs)
                    cls._instances[cls] = instance
        return cls._instances[cls]

    @classmethod
    def clear(mcs, target: type | None = None) -> None:
        """Remove one or all singleton instances.  Needed for test isolation.

        Positional-or-keyword parameter: target (optional).
        """
        with _SINGLETON_LOCK:
            if target is None:
                mcs._instances.clear()
            else:
                mcs._instances.pop(target, None)

    def __repr__(cls) -> str:
        has_instance = cls in SingletonMeta._instances
        return f"<SingletonMeta class={cls.__name__!r} instantiated={has_instance}>"
