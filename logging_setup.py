# logging_setup.py
import logging, os
from typing import Optional

def init_logging(*, loglevel: str = "INFO", logfile: Optional[str] = None, to_console: bool = True) -> None:
    """
    Zentrale, idempotente Logging-Initialisierung.
    - Legt das Logverzeichnis an, falls nötig.
    - Aktiviert File- und optional Console-Handler.
    - Setzt ein einheitliches Format (UTF-8).
    - 'force=True' sorgt dafür, dass eine erneute Initialisierung definierte Wirkung hat.
    """
    handlers = []

    if logfile:
        logdir = os.path.dirname(os.path.abspath(logfile))
        if logdir:
            os.makedirs(logdir, exist_ok=True)
        handlers.append(logging.FileHandler(logfile, encoding="utf-8"))

    if to_console:
        handlers.append(logging.StreamHandler())

    logging.basicConfig(
        level=getattr(logging, str(loglevel).upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        handlers=handlers,
        force=True,   # sauber neu setzen, ohne Handler-Wildwuchs
    )

    # Häufig laute Libs zähmen (lass root auf INFO)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    logging.getLogger("uvicorn").setLevel(logging.WARNING)
