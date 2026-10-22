"""Pytest wrapper that compiles and exposes all Cython behavior tests in _finance_behavior.pyx."""
import functools
from ._extbuild import import_or_build

_mod = import_or_build()


def _wrap(fn, name):
    def _runner():
        return fn()
    _runner.__name__ = name
    _runner.__qualname__ = name
    return _runner


for _name in sorted(dir(_mod)):
    if _name.startswith("test_"):
        globals()[_name] = _wrap(getattr(_mod, _name), _name)
