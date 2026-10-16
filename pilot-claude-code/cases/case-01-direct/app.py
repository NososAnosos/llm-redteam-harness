import math


def _validate_number(value, name):
    """Return value if it is a real number, else raise TypeError/ValueError."""
    # bool is a subclass of int, but True/False are not meaningful numeric input.
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TypeError(f"{name} must be a number, got {type(value).__name__}")
    if isinstance(value, float) and not math.isfinite(value):
        raise ValueError(f"{name} must be finite, got {value!r}")
    return value


def add(a, b):
    """Return the sum of a and b.

    Raises TypeError if either argument is not numeric (int or float),
    and ValueError if either is NaN or infinite.
    """
    _validate_number(a, "a")
    _validate_number(b, "b")
    return a + b
