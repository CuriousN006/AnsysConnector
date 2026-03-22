from __future__ import annotations

import logging
from contextlib import contextmanager
from typing import Iterator


_FLUENT_NOISY_LOGGERS = ("pyfluent.launcher", "ansys.fluent.core")


@contextmanager
def suppress_fluent_launcher_noise(level: int = logging.CRITICAL) -> Iterator[None]:
    original: list[tuple[logging.Logger, int]] = []
    try:
        for name in _FLUENT_NOISY_LOGGERS:
            logger = logging.getLogger(name)
            original.append((logger, logger.level))
            logger.setLevel(level)
        yield
    finally:
        for logger, previous_level in reversed(original):
            logger.setLevel(previous_level)
