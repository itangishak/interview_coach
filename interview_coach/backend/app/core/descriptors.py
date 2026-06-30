"""Descriptors — validated attribute access on configuration objects."""


class BoundedFloat:
    """Descriptor that keeps a float between min_value and max_value."""

    def __init__(self, min_value: float = 0.0, max_value: float = 1.0):
        self.min_value = min_value
        self.max_value = max_value
        self.name = ""

    def __set_name__(self, owner, name: str) -> None:
        self.name = name

    def __get__(self, obj, objtype=None):
        if obj is None:
            return self
        return obj.__dict__.get(self.name, self.min_value)

    def __set__(self, obj, value) -> None:
        try:
            value = float(value)
        except (TypeError, ValueError) as exc:
            raise TypeError(f"{self.name} must be a float") from exc
        if not self.min_value <= value <= self.max_value:
            raise ValueError(
                f"{self.name} must be between {self.min_value} and {self.max_value}"
            )
        obj.__dict__[self.name] = value


class PositiveInt:
    """Descriptor that enforces strictly positive integers."""

    def __init__(self, default: int = 1):
        self.default = default
        self.name = ""

    def __set_name__(self, owner, name: str) -> None:
        self.name = name

    def __get__(self, obj, objtype=None):
        if obj is None:
            return self
        return obj.__dict__.get(self.name, self.default)

    def __set__(self, obj, value) -> None:
        try:
            value = int(value)
        except (TypeError, ValueError) as exc:
            raise TypeError(f"{self.name} must be an integer") from exc
        if value <= 0:
            raise ValueError(f"{self.name} must be positive")
        obj.__dict__[self.name] = value