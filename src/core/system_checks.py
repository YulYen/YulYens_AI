"""Shared system preflight checks.

One deterministic place that answers "is this box ready to run Yul Yen?".
Both the `/healthz` API endpoint (#5) and `launch.py --doctor` (#21) feed off
the same functions so the two never drift apart.

Every check returns a :class:`CheckResult`. Network/subprocess calls are kept in
small standalone functions so they can be mocked in tests without a live Ollama,
Kiwix or GPU.
"""

from __future__ import annotations

import subprocess
from dataclasses import dataclass

import requests

from core.utils import _wiki_mode_enabled

CRITICAL = "critical"
WARNING = "warning"
INFO = "info"


@dataclass
class CheckResult:
    name: str
    ok: bool
    severity: str = INFO  # CRITICAL | WARNING | INFO
    detail: str = ""

    def as_dict(self) -> dict:
        return {
            "name": self.name,
            "ok": self.ok,
            "severity": self.severity,
            "detail": self.detail,
        }


# ---- Individual checks ----------------------------------------------------


def _ollama_base(url: str) -> str:
    return (url or "").rstrip("/")


def check_ollama_reachable(ollama_url: str, timeout: float = 2.0) -> CheckResult:
    base = _ollama_base(ollama_url)
    if not base:
        return CheckResult("ollama", False, CRITICAL, "core.ollama_url is empty")
    try:
        resp = requests.get(f"{base}/api/tags", timeout=timeout)
    except requests.RequestException:
        return CheckResult(
            "ollama", False, CRITICAL, f"unreachable at {base} — is Ollama running?"
        )
    if resp.status_code != 200:
        return CheckResult(
            "ollama", False, CRITICAL, f"{base} returned HTTP {resp.status_code}"
        )
    return CheckResult("ollama", True, CRITICAL, f"reachable at {base}")


def fetch_model_names(ollama_url: str, timeout: float = 2.0) -> list[str]:
    """Lists the installed Ollama models (names carry the ':tag' suffix).

    Raises ``requests.RequestException``/``ValueError`` on connection or
    payload errors — callers decide how to degrade.
    """
    base = _ollama_base(ollama_url)
    resp = requests.get(f"{base}/api/tags", timeout=timeout)
    resp.raise_for_status()
    data = resp.json() or {}
    return [m.get("name", "") for m in data.get("models", [])]


def check_model_available(
    ollama_url: str, model_name: str, timeout: float = 2.0
) -> CheckResult:
    if not model_name:
        return CheckResult("ollama_model", False, CRITICAL, "core.model_name is empty")
    try:
        names = fetch_model_names(ollama_url, timeout)
    except (requests.RequestException, ValueError) as exc:
        return CheckResult(
            "ollama_model", False, CRITICAL, f"could not list models: {exc}"
        )
    # Ollama tags carry the ':tag' suffix; accept a bare name too.
    bare = {n.split(":", 1)[0] for n in names}
    if model_name in names or model_name.split(":", 1)[0] in bare:
        return CheckResult("ollama_model", True, CRITICAL, f"'{model_name}' present")
    return CheckResult(
        "ollama_model",
        False,
        CRITICAL,
        f"'{model_name}' not pulled (run: ollama pull {model_name})",
    )


def check_spacy_model(model_name: str) -> CheckResult:
    try:
        from spacy.util import is_package
    except ImportError as exc:
        return CheckResult("spacy_model", False, WARNING, f"spaCy not installed: {exc}")
    if is_package(model_name):
        return CheckResult("spacy_model", True, WARNING, f"'{model_name}' installed")
    return CheckResult(
        "spacy_model",
        False,
        WARNING,
        f"'{model_name}' missing (run: python -m spacy download {model_name})",
    )


def check_kiwix_reachable(host: str, port, timeout: float = 2.0) -> CheckResult:
    if not host or port in (None, ""):
        return CheckResult(
            "kiwix", False, WARNING, "offline host/kiwix_port not configured"
        )
    target = f"http://{host}:{port}/"
    try:
        requests.get(target, timeout=timeout)
    except requests.RequestException:
        return CheckResult("kiwix", False, WARNING, f"unreachable at {target}")
    return CheckResult("kiwix", True, WARNING, f"reachable at {target}")


def check_vram(timeout: float = 5.0) -> CheckResult:
    try:
        proc = subprocess.run(
            [
                "nvidia-smi",
                "--query-gpu=memory.used,memory.total",
                "--format=csv,noheader,nounits",
            ],
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except (FileNotFoundError, OSError, subprocess.SubprocessError):
        return CheckResult("vram", True, INFO, "no NVIDIA GPU / nvidia-smi unavailable")
    if proc.returncode != 0:
        return CheckResult("vram", True, INFO, "nvidia-smi returned an error")
    line = (proc.stdout or "").strip().splitlines()
    if not line:
        return CheckResult("vram", True, INFO, "nvidia-smi produced no output")
    try:
        used, total = (int(x.strip()) for x in line[0].split(","))
    except (ValueError, IndexError):
        return CheckResult("vram", True, INFO, f"unparseable output: {line[0]!r}")
    pct = (used / total * 100) if total else 0.0
    detail = f"{used}/{total} MiB used ({pct:.0f}%)"
    return CheckResult("vram", pct < 95.0, WARNING, detail)


# ---- Orchestration --------------------------------------------------------


def run_checks(cfg, *, include_vram: bool = True) -> list[CheckResult]:
    """Run every applicable check for the given Config and return the results."""
    results: list[CheckResult] = []

    core = getattr(cfg, "core", {}) or {}
    backend = str(core.get("backend", "ollama") or "ollama").strip().lower()

    if backend == "ollama":
        url = core.get("ollama_url", "")
        reachable = check_ollama_reachable(url)
        results.append(reachable)
        if reachable.ok:
            results.append(check_model_available(url, core.get("model_name", "")))
        else:
            results.append(
                CheckResult(
                    "ollama_model", False, CRITICAL, "skipped: Ollama unreachable"
                )
            )
    else:
        results.append(
            CheckResult("ollama", True, INFO, f"backend='{backend}', Ollama not used")
        )

    wiki = getattr(cfg, "wiki", {}) or {}
    if _wiki_mode_enabled(wiki.get("mode")):
        try:
            from wiki.spacy_keyword_finder import resolve_spacy_model

            results.append(check_spacy_model(resolve_spacy_model(cfg)))
        except (ValueError, ImportError) as exc:
            results.append(
                CheckResult("spacy_model", False, WARNING, f"config error: {exc}")
            )
        if str(wiki.get("mode")).strip().lower() == "offline":
            offline = wiki.get("offline", {}) or {}
            results.append(
                check_kiwix_reachable(offline.get("host"), offline.get("kiwix_port"))
            )
    else:
        results.append(CheckResult("wiki", True, INFO, "wiki disabled"))

    if include_vram:
        results.append(check_vram())

    return results


def overall_status(results: list[CheckResult]) -> str:
    """Aggregate severity: 'error' (critical down), 'degraded' (warning down)."""
    if any(not r.ok and r.severity == CRITICAL for r in results):
        return "error"
    if any(not r.ok and r.severity == WARNING for r in results):
        return "degraded"
    return "ok"
