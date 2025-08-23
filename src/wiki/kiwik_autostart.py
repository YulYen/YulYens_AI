import subprocess, time, requests, logging

logger = logging.getLogger("wiki_proxy")
logger.info("Wiki-Autostart bereit …")

def ensure_kiwix_running_if_offlinemode_and_autostart(cfg):
    """
    Startet kiwix-serve automatisch, wenn:
      - cfg["wiki"]["mode"] == "offline"
      - cfg["wiki"]["offline"]["autostart"] == true
    Gibt True zurück, wenn der Dienst erreichbar ist (lief schon oder erfolgreich gestartet).
    """
    wiki = cfg.wiki
    if wiki["mode"] != "offline":
        return True  # nicht offline → nichts tun

    offline = wiki.get("offline", {})
    if not offline.get("autostart", False):
        return True  # Autostart aus → nichts tun

    host = offline.get("host",)
    port = offline.get("kiwix_port")
    exe  = offline.get("kiwix_exe")
    zim  = offline.get("zim_path")
    timeout_s = offline.get("startup_timeout_s")

    def is_up():
        try:
            requests.get(f"http://{host}:{port}/", timeout=0.5)
            return True
        except Exception:
            return False

    if is_up():
        if logger: logger.info("Kiwix already running on %s:%s", host, port)
        return True

    if not exe or not zim:
        if logger: logger.warning("Kiwix autostart requested, but kiwix_exe/zim_path not set.")
        return False

    try:
        #subprocess.Popen([exe, "--port", str(port), zim])
        subprocess.Popen([exe, f"--port={port}", zim])
        if logger: logger.info("Starting kiwix-serve: %s --port %s %s", exe, port, zim)
    except Exception as e:
        if logger: logger.error("Failed to start kiwix-serve: %s", e)
        return False

    deadline = time.time() + timeout_s
    while time.time() < deadline:
        if is_up():
            if logger: logger.info("Kiwix ready on %s:%s", host, port)
            return True
        time.sleep(0.25)

    if logger: logger.warning("Kiwix did not become ready within %s s.", timeout_s)
    return False