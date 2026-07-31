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
from pathlib import Path

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


def check_kiwix_reachable(host: str | None, port, timeout: float = 2.0) -> CheckResult:
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


# Sektionen, die check_config_schema aus der geladenen Config einsammelt.
_CONFIG_SECTIONS = (
    "core",
    "ui",
    "wiki",
    "logging",
    "api",
    "security",
    "tts",
    "stt",
    "briefing",
    "email_adapter",
    "context_management",
    "evals",
)


def _nvidia_memory(timeout: float = 5.0) -> tuple[int, int] | None:
    """(used, total) in MiB — None, wenn es keine NVIDIA-GPU gibt."""
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
        return None
    if proc.returncode != 0:
        return None
    line = (proc.stdout or "").strip().splitlines()
    if not line:
        return None
    try:
        used, total = (int(x.strip()) for x in line[0].split(","))
    except (ValueError, IndexError):
        return None
    return used, total


def _free_vram_mib(timeout: float = 5.0) -> int | None:
    memory = _nvidia_memory(timeout)
    if memory is None:
        return None
    used, total = memory
    return max(0, total - used)


def check_vram(timeout: float = 5.0) -> CheckResult:
    memory = _nvidia_memory(timeout)
    if memory is None:
        return CheckResult("vram", True, INFO, "no NVIDIA GPU / nvidia-smi unavailable")
    used, total = memory
    pct = (used / total * 100) if total else 0.0
    detail = f"{used}/{total} MiB used ({pct:.0f}%)"
    return CheckResult("vram", pct < 95.0, WARNING, detail)


# ---- Orchestration --------------------------------------------------------


def check_config_schema(cfg) -> CheckResult:
    """Schema-Befunde zu config.yaml und dem gewählten Ensemble (#43).

    Beim Start wird nur gewarnt (siehe config/schema.py) — hier zählt derselbe
    Befund als Fehlschlag. Der Doktor ist der Ort, an dem man Strenge will.
    """
    from config.schema import validate_config, validate_ensemble

    data = {
        key: getattr(cfg, key)
        for key in _CONFIG_SECTIONS
        if getattr(cfg, key, None) is not None
    }
    data["language"] = getattr(cfg, "language", "")
    problems = validate_config(data)

    ensemble = getattr(cfg, "ensemble", None)
    if ensemble:
        problems.extend(
            validate_ensemble(
                Path("ensembles") / str(ensemble), str(getattr(cfg, "language", "de"))
            )
        )

    if not problems:
        return CheckResult("config", True, INFO, "schema ok")
    head = (
        problems[0] if len(problems) == 1 else f"{problems[0]} (+{len(problems) - 1})"
    )
    return CheckResult("config", False, WARNING, head)


def check_model_fits_vram(
    ollama_url: str, model_name: str, timeout: float = 2.0
) -> CheckResult:
    """Vergleicht die Modellgröße aus /api/tags mit dem freien VRAM (#43).

    Rein additiv: ohne erreichbares Ollama oder ohne NVIDIA-GPU bleibt es bei
    einem INFO — der Check soll niemandem den Start vermiesen.
    """
    try:
        base = _ollama_base(ollama_url)
        resp = requests.get(f"{base}/api/tags", timeout=timeout)
        resp.raise_for_status()
        models = (resp.json() or {}).get("models", [])
    except (requests.RequestException, ValueError):
        return CheckResult("model_vram", True, INFO, "Ollama unreachable")

    size_bytes = next(
        (m.get("size") for m in models if m.get("name") == model_name), None
    )
    if not size_bytes:
        return CheckResult("model_vram", True, INFO, f"size for {model_name} unknown")
    needed_gb = int(size_bytes) / 1024**3

    free = _free_vram_mib()
    if free is None:
        return CheckResult(
            "model_vram", True, INFO, f"{model_name} needs ~{needed_gb:.1f} GB"
        )
    free_gb = free / 1024
    detail = f"{model_name} needs ~{needed_gb:.1f} GB, {free_gb:.1f} GB free"
    return CheckResult("model_vram", free_gb >= needed_gb, WARNING, detail)


def run_checks(cfg, *, include_vram: bool = True) -> list[CheckResult]:
    """Run every applicable check for the given Config and return the results."""
    results: list[CheckResult] = []
    results.append(check_config_schema(cfg))

    core = getattr(cfg, "core", {}) or {}
    backend = str(core.get("backend", "ollama") or "ollama").strip().lower()

    if backend == "ollama":
        url = core.get("ollama_url", "")
        reachable = check_ollama_reachable(url)
        results.append(reachable)
        if reachable.ok:
            results.append(check_model_available(url, core.get("model_name", "")))
            results.append(check_model_fits_vram(url, core.get("model_name", "")))
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
