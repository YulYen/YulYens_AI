# launch.py

# Allgemeine Imports
import logging
import os
import socket
import sys
import threading
import time
from datetime import datetime

import uvicorn

# API-Import
from api.app import app, set_provider
from config.config_singleton import Config

# Logging
from config.logging_setup import init_logging

# Core und Konfiguration
from core.factory import AppFactory
from core.utils import _wiki_mode_enabled, ensure_dir_exists
from wiki.kiwix_autostart import ensure_kiwix_running_if_offlinemode_and_autostart
from yaml import YAMLError


def main():

    config_path = "config.yaml"

    try:
        cfg = Config(config_path)  # einmalig laden
    except OSError as exc:
        config_location = os.path.abspath(
            getattr(exc, "filename", config_path) or config_path
        )
        details = exc.strerror or str(exc)
        print(
            (
                "[Yul Yens AI] Critical error: Configuration file "
                f"'{config_location}' could not be loaded ({details}). "
                "Please check the path and access permissions."
            ),
            file=sys.stderr,
        )
        sys.exit(2)
    except YAMLError as exc:
        config_location = os.path.abspath(config_path)
        print(
            (
                "[Yul Yens AI] Critical error: Configuration file "
                f"'{config_location}' contains invalid YAML ({exc}). "
                "Please fix the file."
            ),
            file=sys.stderr,
        )
        sys.exit(3)

    # 1) Logging ZUERST initialisieren
    ensure_dir_exists(cfg.logging["dir"])
    logfile = os.path.join(
        cfg.logging["dir"], f"yulyen_ai_{datetime.now().strftime('%Y-%m-%d_%H-%M')}.log"
    )
    init_logging(
        loglevel=str(cfg.logging["level"]),
        logfile=logfile,
        to_console=bool(cfg.logging["to_console"]),
    )
    logging.info("BOOT OK – Logging initialised and active.")

    # Optional (extra sicher): httpx/urllib3 auf WARNING drehen
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("urllib3").setLevel(logging.WARNING)

    # 2) Wiki-Proxy nur starten, wenn Modus aktiv
    wiki_mode = cfg.wiki["mode"]
    if _wiki_mode_enabled(wiki_mode):
        start_wiki_proxy_thread()
        # Neu: Offline-Wiki bei Bedarf starten
        try:
            ok = ensure_kiwix_running_if_offlinemode_and_autostart(cfg)
            if not ok:
                logging.warning(
                    "Offline-Wiki autostart requested but not available. Continuing without it."
                )
        except Exception as e:
            logging.error(f"Unexpected error during kiwix autostart. Continuing. {e}")

    # 3) Objekte bauen (Factory) – ohne zu starten
    factory = AppFactory()
    ui = factory.get_ui()
    api_provider = factory.get_api_provider()

    logging.info(
        f"ui.type={cfg.ui['type']} wiki.mode={wiki_mode} snippet_limit={cfg.wiki['snippet_limit']}"
    )

    # 4) API optional starten
    if api_provider:
        start_api_in_background(cfg.api, api_provider)

    # 5) UI starten oder (API-only) blockieren
    if cfg.ui["type"] is None:
        print("[Yul Yens AI] API is running. UI is disabled (ui.type = null).")
        threading.Event().wait()
        return
    else:
        ui.launch()  # TerminalUI oder WebUI


def start_api_in_background(api_cfg, provider):
    """
    Starts Uvicorn in a daemon thread.
    """
    set_provider(provider)
    host = api_cfg["host"]
    port = int(api_cfg["port"])

    def _run():
        uvicorn.run(
            app, host=host, port=port, log_level="warning"
        )  # info-level logs disrupt the terminal UI

    t = threading.Thread(target=_run, name="LeahAPI", daemon=True)
    t.start()
    return t


def _wait_for_port(host: str, port: int, timeout: float = 5.0) -> bool:
    """Briefly waits for a TCP port to become reachable (best effort)."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with socket.create_connection((host, port), timeout=0.5):
                return True
        except OSError:
            time.sleep(0.1)
    return False


def start_wiki_proxy_thread() -> threading.Thread | None:
    proxy_port = int(Config().wiki["proxy_port"])

    # Already running? (e.g. started manually)
    if _wait_for_port("127.0.0.1", proxy_port, timeout=0.2):
        logging.info(
            f"Wiki proxy already seems to be running (port {proxy_port} is reachable)."
        )
        return None

    # Start in the same process as a thread
    import wiki.wikipedia_proxy as wiki_proxy  # nutzt die in wikipedia-proxy.py gesetzten Konfigwerte

    t = threading.Thread(target=wiki_proxy.run, name="WikiProxy", daemon=True)
    t.start()

    # Briefly wait for readiness (best effort)
    if _wait_for_port("127.0.0.1", proxy_port, timeout=3.0):
        logging.info(f"Wiki proxy started in thread (port {proxy_port}).")
    else:
        logging.warning(f"Wiki proxy (port {proxy_port}) still unreachable after 3s.")

    return t


if __name__ == "__main__":
    main()
