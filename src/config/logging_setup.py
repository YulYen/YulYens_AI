"""Logging setup module for yulyen_ai.

This module configures separate loggers for the wiki proxy and for all other
components.  The wiki proxy logger writes to its own file and does not
propagate messages to the root logger.  All other log messages propagate to
the root logger, which writes to the primary log file (and optionally the
console).
"""

from __future__ import annotations

import logging
from pathlib import Path
from datetime import datetime
from typing import Optional


def init_logging(
    *,
    loglevel: str = "INFO",
    logfile: Optional[str] = None,
    wiki_proxy_logfile: Optional[str] = None,
    to_console: bool,
) -> None:
    """Initialise application-wide logging.

    Args:
        loglevel: The minimum severity level to record (e.g. ``"INFO"`` or
            ``"DEBUG"``).
        logfile: Path to the main log file for all components except the wiki
            proxy.  If omitted or ``None``, a default name based on the
            current date and time is used.
        wiki_proxy_logfile: Path to the separate log file for the wiki proxy
            component.  If omitted or ``None``, a default name is used.
        to_console: If ``True``, logs will also be emitted to the console
            (stderr).

    The function creates the ``logs/`` directory if it does not already exist
    and configures handlers accordingly.  The wiki proxy logger is isolated
    from the root logger; its messages do not propagate to the root handlers.
    """
    # Prepare the logs directory
    Path("logs").mkdir(exist_ok=True)

    # Determine default log file names if not provided
    now_str = datetime.now().strftime("%Y-%m-%d_%H-%M")
    if logfile is None:
        logfile = f"logs/yulyen_ai_{now_str}.log"
        
    if wiki_proxy_logfile is None:
        wiki_proxy_logfile = f"logs/wiki_proxy_{now_str}.log"

    # Configure the root logger (everything except wiki proxy)
    root_logger = logging.getLogger()
    level = getattr(logging, loglevel.upper(), logging.INFO)
    root_logger.setLevel(level)
    # Remove any existing handlers to avoid duplicate logs
    for handler in list(root_logger.handlers):
        root_logger.removeHandler(handler)

    # File handler for the root logger
    root_handler = logging.FileHandler(logfile, encoding="utf-8")
    root_formatter = logging.Formatter(
        "%(asctime)s %(levelname)s %(name)s: %(message)s", "%Y-%m-%d %H:%M:%S"
    )
    root_handler.setFormatter(root_formatter)
    root_logger.addHandler(root_handler)

    # Optional console handler for the root logger
    if to_console:
        console_handler = logging.StreamHandler()
        console_handler.setFormatter(root_formatter)
        root_logger.addHandler(console_handler)

    # Configure a separate logger for the wiki proxy
    proxy_logger = logging.getLogger("wiki_proxy")
    proxy_logger.setLevel(level)
    proxy_logger.propagate = False
    # Remove any existing handlers (e.g., from previous initialisations)
    for handler in list(proxy_logger.handlers):
        proxy_logger.removeHandler(handler)

    proxy_handler = logging.FileHandler(wiki_proxy_logfile, encoding="utf-8")
    proxy_formatter = logging.Formatter(
        "%(asctime)s %(levelname)s wiki_proxy: %(message)s", "%Y-%m-%d %H:%M:%S"
    )
    proxy_handler.setFormatter(proxy_formatter)
    proxy_logger.addHandler(proxy_handler)
