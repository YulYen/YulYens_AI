# jk_ki_main.py

# Allgemeine Imports
import os, logging, socket
from datetime import datetime
import threading
import uvicorn
import time
import socket

# API-Import
from api.app import app, set_provider

# Logging
from logging_setup import init_logging

# Core und Konfiguration
from core.factory import AppFactory
from core import utils
from config_singleton import Config


def main():
    cfg = Config()  # einmalig laden

    # 1) Logging ZUERST initialisieren
    os.makedirs(cfg.logging["dir"], exist_ok=True)
    logfile = os.path.join(
        cfg.logging["dir"],
        f"yulyen_ai_{datetime.now().strftime('%Y-%m-%d_%H-%M')}.log"
    )
    init_logging(
        loglevel=str(cfg.logging["level"]),
        logfile=logfile,
        to_console=bool(cfg.logging["to_console"]),
    )

    # Optional (extra sicher): httpx/urllib3 auf WARNING drehen
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("urllib3").setLevel(logging.WARNING)

    # 2) Wiki-Proxy nur starten, wenn Modus aktiv
    wiki_mode = cfg.wiki["mode"]
    if utils._wiki_mode_enabled(wiki_mode):
        start_wiki_proxy_thread()

    # 3) Objekte bauen (Factory) – ohne zu starten
    factory = AppFactory()
    ui = factory.get_ui()
    api_provider = factory.get_api_provider()

    logging.info(f"ui.type={cfg.ui['type']} wiki.mode={wiki_mode} snippet_limit={cfg.wiki['snippet_limit']}")

    # 4) API optional starten
    if api_provider:
        start_api_in_background(cfg.api, api_provider)

    # 5) UI starten oder (API-only) blockieren
    if cfg.ui["type"] is None:
        print("[Yul Yens AI] API läuft. UI ist deaktiviert (ui.type = null).")
        threading.Event().wait()
        return
    else:
        ui.launch()  # TerminalUI oder WebUI


def start_api_in_background(api_cfg, provider):
    """
    Startet Uvicorn in einem Daemon-Thread.
    """
    set_provider(provider)
    host = api_cfg["host"]
    port = int(api_cfg["port"])

    def _run():
        uvicorn.run(app, host=host, port=port, log_level="warning") # bei Info wird die TerminalUI gestört

    t = threading.Thread(target=_run, name="LeahAPI", daemon=True)
    t.start()
    return t

def _wait_for_port(host: str, port: int, timeout: float = 5.0) -> bool:
    """Wartet kurz, bis ein TCP-Port erreichbar ist (Best‑Effort)."""
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

    # Bereits laufend? (z. B. manuell gestartet)
    if _wait_for_port("127.0.0.1", proxy_port, timeout=0.2):
        logging.info(f"Wiki-Proxy scheint schon zu laufen (Port {proxy_port} ist erreichbar).")
        return None

    # Im selben Prozess als Thread starten
    import wikipedia_proxy as wiki_proxy  # nutzt die in wikipedia-proxy.py gesetzten Konfigwerte
    t = threading.Thread(target=wiki_proxy.run, name="WikiProxy", daemon=True)
    t.start()

    # Kurz auf Readiness warten (best-effort)
    if _wait_for_port("127.0.0.1", proxy_port, timeout=3.0):
        logging.info(f"Wiki-Proxy im Thread gestartet (Port {proxy_port}).")
    else:
        logging.warning(f"Wiki-Proxy (Port {proxy_port}) nach 3s noch nicht erreichbar.")

    return t

if __name__ == "__main__":
    main()