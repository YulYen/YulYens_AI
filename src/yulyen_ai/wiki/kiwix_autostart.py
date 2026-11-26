import ipaddress
import logging
import subprocess
import time

import requests

logger = logging.getLogger("wiki_proxy")
logger.info("Wiki autostart initialized")


def ensure_kiwix_running_if_offlinemode_and_autostart(cfg):
    """
    Automatically starts kiwix-serve when:
      - cfg["wiki"]["mode"] == "offline"
      - cfg["wiki"]["offline"]["autostart"] == True
    Returns True when the service is reachable (already running or started successfully).
    """
    wiki = cfg.wiki
    if wiki["mode"] != "offline":
        return True  # Mode is not offline, so there is nothing to do.

    offline = wiki.get("offline", {})
    if not offline.get("autostart", False):
        return True  # Autostart is disabled, so there is nothing to do.

    host = offline.get("host")
    port = offline.get("kiwix_port")
    exe = offline.get("kiwix_exe")
    zim = offline.get("zim_path")
    timeout_s = offline.get("startup_timeout_s")

    if not host or port in (None, ""):
        logger.error(
            "Kiwix autostart requested, but host (%s) or kiwix_port (%s) missing.",
            host,
            port,
        )
        return False

    def is_up():
        try:
            requests.get(f"http://{host}:{port}/", timeout=0.5)
            return True
        except Exception:
            return False

    if is_up():
        logger.info("Kiwix already running on %s:%s", host, port)
        return True

    if not exe or not zim:
        logger.warning("Kiwix autostart requested, but kiwix_exe/zim_path not set.")
        return False

    command = [exe, f"--port={port}", *_address_argument(host), zim]
    try:
        subprocess.Popen(command)
        logger.info("Starting kiwix-serve: %s", " ".join(command))
    except Exception as e:
        logger.error("Failed to start kiwix-serve: %s", e)
        return False

    deadline = time.time() + timeout_s
    while time.time() < deadline:
        if is_up():
            logger.info("Kiwix ready on %s:%s", host, port)
            return True
        time.sleep(0.25)

    logger.warning("Kiwix did not become ready within %s s.", timeout_s)
    return False


def _address_argument(host) -> list[str]:
    """`--address=<ip>`, damit kiwix-serve nur dort lauscht, wo die Config es will.

    Ohne das Argument bindet kiwix-serve an **alle** Schnittstellen — die
    Offline-Wikipedia war damit im ganzen LAN lesbar, obwohl
    `wiki.offline.host` auf `127.0.0.1` steht (#83). `--address` nimmt nur
    eine IP: steht in der Config ein Name wie `localhost`, bleibt das Argument
    weg und eine Warnung sagt, warum der Server dann überall lauscht.
    """
    try:
        ipaddress.ip_address(str(host))
    except ValueError:
        logger.warning(
            "wiki.offline.host ist '%s' und keine IP-Adresse — kiwix-serve wird "
            "ohne --address gestartet und lauscht auf allen Schnittstellen.",
            host,
        )
        return []
    return [f"--address={host}"]
