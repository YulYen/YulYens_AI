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
        if logger:
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
        if logger:
            logger.info("Kiwix already running on %s:%s", host, port)
        return True

    if not exe or not zim:
        if logger:
            logger.warning("Kiwix autostart requested, but kiwix_exe/zim_path not set.")
        return False

    try:
        # subprocess.Popen([exe, "--port", str(port), zim])
        subprocess.Popen([exe, f"--port={port}", zim])
        if logger:
            logger.info("Starting kiwix-serve: %s --port %s %s", exe, port, zim)
    except Exception as e:
        if logger:
            logger.error("Failed to start kiwix-serve: %s", e)
        return False

    deadline = time.time() + timeout_s
    while time.time() < deadline:
        if is_up():
            if logger:
                logger.info("Kiwix ready on %s:%s", host, port)
            return True
        time.sleep(0.25)

    if logger:
        logger.warning("Kiwix did not become ready within %s s.", timeout_s)
    return False
