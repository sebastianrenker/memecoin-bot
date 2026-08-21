"""Strategy package. Importing it registers every strategy module so the
name->class registry (strategies.base) is fully populated.
"""
from __future__ import annotations

import importlib
import pkgutil

from strategies.base import (  # noqa: F401
    Strategy, register, build_strategy, available_strategies,
)

# Auto-import every submodule (except base/this) so @register runs.
for _m in pkgutil.iter_modules(__path__):
    if _m.name not in ("base", "__init__"):
        importlib.import_module(f"{__name__}.{_m.name}")
