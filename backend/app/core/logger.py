# This file exists for IDE compatibility.
# The actual logger is in app/core/logging.py
# If you see import errors for "app.core.logger", add this alias.
from app.core.logging import get_logger, configure_logging

__all__ = ["get_logger", "configure_logging"]
