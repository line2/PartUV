try:
    from ._core import *           # compiled extension
except ImportError:
    print("ERROR: _core.so not found")
    print("HINT: are your running python -m demo.partuv_demo at the root folder of the project? This sometimes routes `import partuv` to the local path. Go to demo folder if needed.")
    raise ImportError("ImportError: _core.so not found")

__version__ = "0.2.0"

from .api import unwrap, prepare, UnwrapResult, UnwrapStats, PrepareResult, DEFAULT_CONFIG

# `partuv.preprocess` and `partuv.save_results` stay importable, but loading the module
# pulls torch (PartField), so it is deferred: `import partuv` must stay cheap for the
# geometry-only users who never run preprocessing.
_LAZY = {"preprocess", "save_results"}


def __getattr__(name):
    if name in _LAZY:
        from . import preprocess as _p
        return getattr(_p, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def __dir__():
    return sorted(set(globals()) | _LAZY)


__all__ = [n for n in dir() if not n.startswith("_")] + sorted(_LAZY)
