# logging_setup.py
import logging

def init_logging(loglevel="INFO", logfile=None, to_console=True):
    logging.basicConfig(
        level=getattr(logging, loglevel),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        handlers=[logging.FileHandler(logfile, encoding="utf-8")] + ([logging.StreamHandler()] if to_console else []), force=True)