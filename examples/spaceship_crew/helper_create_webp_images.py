from pathlib import Path
from PIL import Image

# Basisverzeichnis, alle Unterordner werden durchsucht
BASE_DIR = Path("examples/spaceship_crew/static")

# Einstellungen
FULL_QUALITY = 90
THUMB_SIZE = (400, 400)

for img_path in BASE_DIR.rglob("*.*"):
    if img_path.suffix.lower() not in [".jpg", ".jpeg", ".png", ".webp"]:
        continue

    try:
        # Ausgabeziele im selben Ordner wie Original
        out_full = img_path.parent / "full.webp"
        out_thumb = img_path.parent / "thumb.webp"

        # Bild laden
        with Image.open(img_path) as im:
            # Full-Version
            im.convert("RGB").save(out_full, "webp", quality=FULL_QUALITY)

            # Thumbnail-Version
            thumb = im.copy()
            thumb.thumbnail(THUMB_SIZE)
            thumb.convert("RGB").save(out_thumb, "webp", quality=80)

        print(f"✔ {img_path.relative_to(BASE_DIR)} → full.webp + thumb.webp")
    except Exception as e:
        print(f"⚠ Fehler bei {img_path}: {e}")