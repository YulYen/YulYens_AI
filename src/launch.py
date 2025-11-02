# launch.py

# General imports
import argparse
import logging
import os
import socket
import sys, platform
import threading
import time
from datetime import datetime

import uvicorn

# Logging setup
from config.logging_setup import init_logging

# Core and configuration
from config.config_singleton import Config
from core.factory import AppFactory
from core.utils import _wiki_mode_enabled, ensure_dir_exists
from wiki.kiwix_autostart import ensure_kiwix_running_if_offlinemode_and_autostart
from yaml import YAMLError


def main():

    parser = argparse.ArgumentParser()
    parser.add_argument(
        "-c",
        "--config",
        dest="config",
        help="Path to the YAML configuration file; defaults to ./config.yaml if not specified.",
    )
    parser.add_argument(
        "-e",
        "--ensemble",
        dest="ensemble",
        help="Name of the persona ensemble to load.",
    )
    args = parser.parse_args()
    if not args.ensemble:
        parser.error("Missing required parameter: --ensemble / -e. If you are not sure, use 'python src/launch.py -e classic'")
    config_path = os.path.abspath(args.config or "config.yaml")

    try:
        cfg = Config(path=config_path)  # load once
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

    cfg.ensemble = args.ensemble

    # 1) Initialize logging first
    ensure_dir_exists(cfg.logging["dir"])
    logfile = os.path.join(
        cfg.logging["dir"], f"yulyen_ai_{datetime.now().strftime('%Y-%m-%d_%H-%M')}.log"
    )
    to_console = cfg.logging["to_console"] == "true" or (cfg.logging["to_console"] == "auto" and cfg.ui["type"] != "terminal")
    init_logging(
        loglevel=str(cfg.logging["level"]),
        logfile=logfile,
        to_console=to_console,
    )
    logging.info(f"Using configuration file: {config_path}")
    logging.info("BOOT OK – Logging initialised and active.")
    logging.info(f"Python exe: {sys.executable}  version: {platform.python_version()}")


    # Optional: set httpx/urllib3 to WARNING for extra safety
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("urllib3").setLevel(logging.WARNING)

    # 2) Start the wiki proxy only if the mode is active
    wiki_mode = cfg.wiki["mode"]
    if _wiki_mode_enabled(wiki_mode):
        start_wiki_proxy_thread()
        # New: start the offline wiki if requested
        try:
            ok = ensure_kiwix_running_if_offlinemode_and_autostart(cfg)
            if not ok:
                logging.warning(
                    "Offline-Wiki autostart requested but not available. Continuing without it."
                )
        except Exception as e:
            logging.error(f"Unexpected error during kiwix autostart. Continuing. {e}")

    # 3) Build objects (Factory) without starting them
    factory = AppFactory()
    ui = factory.get_ui()
    api_provider = factory.get_api_provider()

    logging.info(
        f"ui.type={cfg.ui['type']} wiki.mode={wiki_mode} snippet_limit={cfg.wiki['snippet_limit']}"
    )

    # 4) Optionally start the API
    if api_provider:
        start_api_in_background(cfg.api, api_provider)

    # 5) Start the UI or block if API-only
    if cfg.ui["type"] is None:
        print("[Yul Yens AI] API is running. UI is disabled (ui.type = null).")
        threading.Event().wait()
        return
    else:
        ui.launch()  # Terminal UI or Web UI


def start_api_in_background(api_cfg, provider):
    """
    Starts Uvicorn in a daemon thread.
    """
    from api.app import app, set_provider

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
    import wiki.wikipedia_proxy as wiki_proxy  # uses the configuration set in wikipedia-proxy.py

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
