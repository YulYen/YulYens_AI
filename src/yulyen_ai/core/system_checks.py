"""Shared system preflight checks.

One deterministic place that answers "is this box ready to run Yul Yen?".
Both the `/healthz` API endpoint (#5) and `launch.py --doctor` (#21) feed off
the same functions so the two never drift apart.

Every check returns a :class:`CheckResult`. Network/subprocess calls are kept in
small standalone functions so they can be mocked in tests without a live Ollama,
Kiwix or GPU.
"""

from __future__ import annotations

import logging
import subprocess
from dataclasses import dataclass
from pathlib import Path

import requests

from yulyen_ai.core.utils import wiki_mode_enabled

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
    "email_adapter",
    "context_management",
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
    from yulyen_ai.config.schema import validate_config, validate_ensemble

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


def _is_moe(base: str, model_name: str, timeout: float = 2.0) -> bool:
    """Ist das Modell ein Mixture-of-Experts? Auskunft gibt ``/api/show`` (#99f).

    Erkennbar an einem ``<familie>.expert_count`` in ``model_info``
    (``gemma4.expert_count`` 128, ``qwen35moe.expert_count`` 256); dichte
    Modelle wie ministral-3 haben den Schlüssel nicht. Im Zweifel ``False`` —
    dann bleibt es bei der Warnung wie bisher.
    """
    try:
        resp = requests.post(
            f"{base}/api/show", json={"model": model_name}, timeout=timeout
        )
        resp.raise_for_status()
        info = (resp.json() or {}).get("model_info") or {}
    except (requests.RequestException, ValueError, AttributeError):
        return False
    for key, value in info.items():
        if str(key).endswith(".expert_count"):
            try:
                return int(value) > 1
            except (TypeError, ValueError):
                return False
    return False


def _loaded_vram_mib(base: str, model_name: str, timeout: float = 2.0) -> int:
    """VRAM, den das Modell schon belegt, weil Ollama es geladen hat (#99f).

    Ohne diese Zahl warnt der Check gegen sich selbst: Das geladene Modell
    zählt in nvidia-smi als belegt, also fehlt sein eigener Platz im „frei".
    """
    try:
        resp = requests.get(f"{base}/api/ps", timeout=timeout)
        resp.raise_for_status()
        running = (resp.json() or {}).get("models", [])
    except (requests.RequestException, ValueError, AttributeError):
        return 0
    for entry in running:
        if model_name in (entry.get("name"), entry.get("model")):
            try:
                return int(entry.get("size_vram") or 0) // 1024**2
            except (TypeError, ValueError):
                return 0
    return 0


def check_model_fits_vram(
    ollama_url: str, model_name: str, timeout: float = 2.0
) -> CheckResult:
    """Vergleicht die Modellgröße aus /api/tags mit dem freien VRAM (#43).

    Rein additiv: ohne erreichbares Ollama oder ohne NVIDIA-GPU bleibt es bei
    einem INFO — der Check soll niemandem den Start vermiesen.

    Seit #99f zwei Ausnahmen: Ein schon geladenes Modell bekommt seinen
    eigenen VRAM als frei gutgeschrieben, und ein MoE-Modell, das nicht ganz
    passt, ist nur ein INFO — bei ihm darf ein Teil im Arbeitsspeicher liegen
    (gemma4:26b auf 16 GB: langsamer Kaltstart, danach kaum spürbar).
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
    free_gb = (free + _loaded_vram_mib(base, model_name, timeout)) / 1024
    detail = f"{model_name} needs ~{needed_gb:.1f} GB, {free_gb:.1f} GB free"
    if free_gb >= needed_gb:
        return CheckResult("model_vram", True, WARNING, detail)
    if _is_moe(base, model_name, timeout):
        return CheckResult(
            "model_vram",
            True,
            INFO,
            f"{detail} — MoE, part of it may sit in system RAM (slower cold start)",
        )
    return CheckResult("model_vram", False, WARNING, detail)


def _solo_models(default_model: str) -> dict[str, str]:
    """Persona → eigenes Solo-Modell, nur wo es vom Default abweicht (#85).

    Ohne lesbares Ensemble gibt es nichts zu prüfen — das meldet bereits die
    Schema-Prüfung, eine zweite Fehlermeldung hier wäre nur Lärm.
    """
    from yulyen_ai.config import personas

    try:
        names = personas.get_all_persona_names()
        models = {name: personas.get_model(name) for name in names}
    except Exception:  # noqa: BLE001 — Diagnose darf nicht selbst abbrechen
        logging.debug("Solo-Modelle nicht lesbar", exc_info=True)
        return {}
    return {
        name: model
        for name, model in models.items()
        if model and model != default_model
    }


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
            # Solo-Modelle (#85): fehlt eins, scheitert genau das Solo dieser
            # Persona — so hart wie das Default-Modell, nur später.
            for persona, model in _solo_models(core.get("model_name", "")).items():
                check = check_model_available(url, model)
                results.append(
                    CheckResult(
                        f"solo_model[{persona}]", check.ok, check.severity, check.detail
                    )
                )
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
    if wiki_mode_enabled(wiki.get("mode")):
        try:
            from yulyen_ai.wiki.spacy_keyword_finder import resolve_spacy_model

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
