#!/usr/bin/env python3
"""Generate WebP persona assets from the existing PNG sources.

The repository intentionally avoids committing binary image assets. This helper
script converts the PNG persona images referenced in ``personas_base.yaml`` into
static WebP thumbnails and full-size previews that the Gradio UI can serve.

Usage:
    pip install Pillow
    python scripts/generate_persona_assets.py [--force]

The script reads the configured personas, picks up their ``image_path`` entries
(relative to the repository root) and creates ``thumb.webp`` / ``full.webp``
artifacts inside ``assets/personas/<PERSONA>/``. Existing files are skipped by
default; pass ``--force`` to overwrite them.
"""
from __future__ import annotations

import argparse
from pathlib import Path
from typing import Iterable, Tuple

import yaml
from PIL import Image


REPO_ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = REPO_ROOT / "src" / "config" / "personas_base.yaml"
ASSETS_DIR = REPO_ROOT / "assets" / "personas"

THUMB_SIZE = 320
FULL_SIZE = 1024
WEBP_SAVE_ARGS = {"format": "WEBP", "quality": 95, "method": 6}


def _resolve_source(path: Path) -> Path:
    if path.exists():
        return path

    parent = path.parent
    target_name = path.name.lower()
    for candidate in parent.glob("*"):
        if candidate.name.lower() == target_name:
            return candidate

    raise FileNotFoundError(f"Persona source image missing: {path}")


def _load_persona_sources() -> Iterable[Tuple[str, Path]]:
    data = yaml.safe_load(CONFIG_PATH.read_text(encoding="utf-8"))
    personas = data.get("personas", [])
    for entry in personas:
        name = entry["name"]
        image_path = entry["image_path"]
        yield name, _resolve_source(REPO_ROOT / image_path)


def _prepare_image(source: Path) -> Image.Image:
    with Image.open(source) as img:
        return img.convert("RGBA")


def _save_variant(img: Image.Image, target: Path, max_size: int | None) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    variant = img.copy()
    if max_size:
        variant.thumbnail((max_size, max_size), Image.Resampling.LANCZOS)
    variant.save(target, **WEBP_SAVE_ARGS)


def generate_assets(force: bool = False) -> None:
    for persona, source in _load_persona_sources():
        prepared = _prepare_image(source)

        persona_dir = ASSETS_DIR / persona.upper()
        thumb_target = persona_dir / "thumb.webp"
        full_target = persona_dir / "full.webp"

        if not force and thumb_target.exists() and full_target.exists():
            print(f"Skipping {persona}: assets already exist")
            continue

        relative_source = source.relative_to(REPO_ROOT)
        print(f"Generating assets for {persona} from {relative_source}")

        _save_variant(prepared, thumb_target, THUMB_SIZE)
        _save_variant(prepared, full_target, FULL_SIZE)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--force",
        action="store_true",
        help="Overwrite existing WebP assets instead of skipping them.",
    )
    args = parser.parse_args()
    generate_assets(force=args.force)


if __name__ == "__main__":
    main()
