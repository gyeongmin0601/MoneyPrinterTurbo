"""
Download Noto Sans KR Bold font for Korean subtitle rendering.

Usage:
    python scripts/download_korean_font.py

Downloads NotoSansKR-Bold.ttf to resource/fonts/ directory.
"""

import os
import sys
import requests

FONT_URL = "https://github.com/google/fonts/raw/main/ofl/notosanskr/NotoSansKR%5Bwght%5D.ttf"
FONT_FILENAME = "NotoSansKR-Bold.ttf"


def get_fonts_dir():
    script_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.dirname(script_dir)
    fonts_dir = os.path.join(project_root, "resource", "fonts")
    os.makedirs(fonts_dir, exist_ok=True)
    return fonts_dir


def download_font():
    fonts_dir = get_fonts_dir()
    font_path = os.path.join(fonts_dir, FONT_FILENAME)

    if os.path.exists(font_path):
        print(f"Font already exists: {font_path}")
        return font_path

    print(f"Downloading {FONT_FILENAME}...")
    try:
        resp = requests.get(FONT_URL, timeout=30, stream=True)
        resp.raise_for_status()

        with open(font_path, "wb") as f:
            for chunk in resp.iter_content(chunk_size=8192):
                f.write(chunk)

        file_size = os.path.getsize(font_path)
        print(f"Downloaded: {font_path} ({file_size:,} bytes)")
        return font_path
    except Exception as e:
        print(f"Failed to download font: {e}")
        print(f"You can manually download from: https://fonts.google.com/noto/specimen/Noto+Sans+KR")
        print(f"Place the file as: {font_path}")
        return None


if __name__ == "__main__":
    result = download_font()
    sys.exit(0 if result else 1)
