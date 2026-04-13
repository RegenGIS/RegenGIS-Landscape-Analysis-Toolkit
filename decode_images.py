"""Decode base64 placeholder images into PNG files.

Run this script in the plugin folder to create `icon.png` and `screenshot.png`.
"""
import base64
from pathlib import Path

base_dir = Path(__file__).parent

for name in ("icon.png.b64", "screenshot.png.b64"):
    b64_path = base_dir / name
    out_path = base_dir / name.replace(".b64", "")
    if not b64_path.exists():
        print(f"Missing {b64_path}")
        continue
    data = b64_path.read_text().strip()
    out_path.write_bytes(base64.b64decode(data))
    print(f"Wrote {out_path}")
