from numbers import Number


def _require_number(value, name):
    """Raise TypeError unless value is a real number (bool is rejected)."""
    if isinstance(value, bool) or not isinstance(value, Number):
        raise TypeError(f"{name} must be numeric, got {type(value).__name__}")


def add(a, b):
    """Return the sum of a and b. Raises TypeError for non-numeric input."""
    _require_number(a, "a")
    _require_number(b, "b")
    return a + b
