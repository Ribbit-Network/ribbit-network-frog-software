"""
Minimal mock implementation for MicroPython testing.

This provides a basic implementation of mock objects to replace unittest.mock
which is not available in MicroPython.
"""

class MagicMock:
    """A simple mock class that records calls and returns configurable values."""
    
    def __init__(self, return_value=None):
        self._return_value = return_value
        self._calls = []
        self._call_args = []
        self._call_kwargs = []
        self._attributes = {}
        
    def __call__(self, *args, **kwargs):
        self._calls.append((args, kwargs))
        self._call_args.append(args)
        self._call_kwargs.append(kwargs)
        return self._return_value
        
    def __getattr__(self, name):
        if name not in self._attributes:
            self._attributes[name] = MagicMock()
        return self._attributes[name]
        
    def assert_called_with(self, *args, **kwargs):
        assert (args, kwargs) in self._calls, f"Expected call with {args}, {kwargs} but got {self._calls}"

    def assert_called(self):
        assert len(self._calls) > 0, "Expected call but not called"


def patch(target, new_object=None):
    """A simplified patch decorator that just returns the patched function."""
    if new_object is None:
        new_object = MagicMock()
    
    class _PatchContext:
        def __init__(self, mock):
            self.mock = mock
            
        def __enter__(self):
            return self.mock
            
        def __exit__(self, exc_type, exc_val, exc_tb):
            pass
    
    # For now, this is just a simple decorator pattern for functions
    # In real tests, we'll just use direct MagicMock objects
    def decorator(func):
        def wrapper(*args, **kwargs):
            return func(*args, **kwargs)
        return wrapper
    
    return _PatchContext(new_object) if callable(getattr(new_object, "__enter__", None)) else decorator