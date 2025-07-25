# logging_setup.py
import logging

def init_logging(loglevel="INFO", logfile=None, to_console=True):
    level = getattr(logging, loglevel.upper(), logging.INFO)
    handlers = []

    if to_console:
        handlers.append(logging.StreamHandler())
    if logfile:
        handlers.append(logging.FileHandler(logfile, encoding="utf-8"))

    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(message)s",
        handlers=handlers
    )