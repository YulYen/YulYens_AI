# logging_setup.py
import logging

NOISY = ["uvicorn", "uvicorn.error", "uvicorn.access", "gradio", "httpx", "urllib3"]

def init_logging(loglevel="INFO", logfile=None, to_console=False):
    # Baue Handlerliste strikt nach to_console
    handlers = []
    if logfile:
        handlers.append(logging.FileHandler(logfile, encoding="utf-8"))
    if to_console:
        handlers.append(logging.StreamHandler())

    logging.basicConfig(
        level=getattr(logging, loglevel.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        handlers=handlers,
        force=True,  # killt alle alten Handler
    )

    # „Laute“ Logger: eigene Handler weg, auf Root propagieren, Level setzen
    for name in NOISY:
        lg = logging.getLogger(name)
        lg.handlers.clear()
        lg.propagate = False
        lg.setLevel(getattr(logging, loglevel.upper(), logging.INFO))

    # Gürtel + Hosenträger: falls jemand später doch noch StreamHandler dranhängt
    if not to_console:
        _remove_console_handlers_from_all_loggers()

def _remove_console_handlers_from_all_loggers():
    """Entfernt StreamHandler aus Root und bekannten Child-Loggern."""
    def _strip_stream_handlers(logger: logging.Logger):
        for h in list(logger.handlers):
            if isinstance(h, logging.StreamHandler):
                logger.removeHandler(h)
    root = logging.getLogger()
    _strip_stream_handlers(root)
    for name, lg in logging.Logger.manager.loggerDict.items():
        if isinstance(lg, logging.PlaceHolder):
            continue
        _strip_stream_handlers(lg)  # type: ignore[arg-type]