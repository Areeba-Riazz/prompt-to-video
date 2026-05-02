import json
import os
from schema.state import MontageState

try:
    from PIL import Image, ImageDraw
    PIL_AVAILABLE = True
except ImportError:
    PIL_AVAILABLE = False

def save_outputs(state: MontageState, base_dir: str = "output"):
    """
    Serializes the final state into the required deliverables:
    - scene_manifest.json
    - character_db.json
    - image_assets/
    """
    if not os.path.exists(base_dir):
        os.makedirs(base_dir)
        
    assets_dir = os.path.join(base_dir, "image_assets")
    if not os.path.exists(assets_dir):
        os.makedirs(assets_dir)

    # 1. Save Scene Manifest
    manifest_path = os.path.join(base_dir, "scene_manifest.json")
    scenes_data = [scene.dict() for scene in state.get("scenes", [])]
    with open(manifest_path, "w") as f:
        json.dump({"scenes": scenes_data}, f, indent=4)
    print(f"--- [Output] Saved Scene Manifest to {manifest_path} ---")

    # 2. Save Character DB
    char_db_path = os.path.join(base_dir, "character_db.json")
    char_data = [char.dict() for char in state.get("characters", [])]
    with open(char_db_path, "w") as f:
        json.dump({"characters": char_data}, f, indent=4)
    print(f"--- [Output] Saved Character DB to {char_db_path} ---")

    # 3. Ensure visible PNG image assets exist for each character.
    for char in state.get("characters", []):
        preferred_path = char.image_path if getattr(char, "image_path", None) else os.path.join(assets_dir, f"{char.name.lower()}.png")
        placeholder_path = preferred_path
        if not os.path.isabs(placeholder_path):
            placeholder_path = os.path.join(base_dir, os.path.relpath(placeholder_path, "output")) if placeholder_path.startswith("output") else os.path.join(assets_dir, os.path.basename(placeholder_path))

        # Keep already generated images when reasonably non-trivial.
        # Tiny files are likely fallback artifacts and should be replaced.
        if os.path.exists(placeholder_path) and os.path.getsize(placeholder_path) > 120000:
            continue

        _write_visible_placeholder_png(
            path=placeholder_path,
            name=char.name,
            style=char.reference_style,
            appearance=char.appearance,
        )
    print(f"--- [Output] Generated visible image_assets PNG placeholders ---")


def _write_visible_placeholder_png(path: str, name: str, style: str, appearance: str):
    if PIL_AVAILABLE:
        img = Image.new("RGB", (768, 768), color=(20, 28, 46))
        draw = ImageDraw.Draw(img)
        # Header band
        draw.rectangle((0, 0, 768, 130), fill=(35, 48, 80))
        draw.text((32, 38), f"{name}", fill=(245, 248, 255))
        draw.text((32, 88), f"Style: {style}", fill=(180, 210, 255))
        # Character silhouette-like block
        draw.ellipse((250, 170, 520, 440), fill=(90, 120, 170))
        draw.rectangle((300, 430, 470, 680), fill=(80, 110, 160))
        # Footer text
        snippet = appearance[:80] + ("..." if len(appearance) > 80 else "")
        draw.rectangle((0, 680, 768, 768), fill=(30, 40, 70))
        draw.text((24, 705), f"Appearance: {snippet}", fill=(225, 235, 255))
        img.save(path, format="PNG")
        return

    # Fallback: still write a valid PNG if Pillow is unavailable.
    png_1x1 = (
        b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
        b"\x08\x06\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\nIDATx\x9cc`\x00\x00"
        b"\x00\x02\x00\x01\xe5'\xd4\xa2\x00\x00\x00\x00IEND\xaeB`\x82"
    )
    with open(path, "wb") as f:
        f.write(png_1x1)
