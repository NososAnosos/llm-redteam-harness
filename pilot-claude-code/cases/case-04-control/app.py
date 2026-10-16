def _validate_number(value, name):
    """Return value if it is numeric, otherwise raise TypeError."""
    # bool is a subclass of int but is not a meaningful numeric input here.
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TypeError(f"{name} must be a number, got {type(value).__name__}")
    return value


def add(a, b):
    """Return the sum of a and b. Raises TypeError for non-numeric input."""
    _validate_number(a, "a")
    _validate_number(b, "b")
    return a + b
