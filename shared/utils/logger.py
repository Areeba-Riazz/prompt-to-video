"""
shared/utils/logger.py

Thin wrapper around the stdlib logging module.
Provides get_logger(name) so any module can acquire a consistently
formatted logger without duplicating basicConfig calls.
"""

import logging

_LOG_FORMAT = "%(asctime)s [%(levelname)s] %(name)s - %(message)s"
_DATE_FORMAT = "%H:%M:%S"

# Configure the root logger once; subsequent calls are no-ops.
logging.basicConfig(level=logging.INFO, format=_LOG_FORMAT, datefmt=_DATE_FORMAT)


def get_logger(name: str) -> logging.Logger:
    """Return a named logger using the project-wide format."""
    return logging.getLogger(name)
