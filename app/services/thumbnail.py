"""
Thumbnail generation service.

Supports two modes:
1. LLM-generated prompt → external image API (DALL-E, etc.)
2. Programmatic generation using Pillow (text overlay on solid/gradient background)

Mode 2 works offline without any API key.
"""

import json
import os
import re
from typing import Optional

import requests
from loguru import logger

from app.config import config
from app.services import llm
from app.utils import utils


def generate_thumbnail_prompt(
    video_subject: str,
    title_text: str = "",
    language: str = "ko",
) -> str:
    prompt = f"""
# Role: YouTube Thumbnail Designer

## Task
Generate a detailed image generation prompt for a YouTube video thumbnail.

## Video Subject
{video_subject}

## Title Text (to display on thumbnail)
{title_text or video_subject}

## Requirements
1. The prompt should describe a visually striking, click-worthy thumbnail
2. Use bold colors, high contrast, clear focal point
3. Style: modern, clean, professional YouTube thumbnail
4. Include text overlay suggestion if appropriate
5. Aspect ratio: 16:9 (1280x720)
6. Do NOT include any text in the image itself - text will be added separately

## Output
Return ONLY the image generation prompt as a single string, nothing else.
Example: "A dramatic split-screen showing a luxury car on one side and a piggy bank on the other, vibrant neon blue and orange color scheme, 3D rendered, cinematic lighting, 16:9 aspect ratio"
""".strip()

    for i in range(3):
        try:
            response = llm._generate_response(prompt)
            if response and "Error: " not in response:
                clean = response.strip().strip('"').strip("'")
                logger.success(f"generated thumbnail prompt: {clean[:100]}...")
                return clean
        except Exception as e:
            logger.warning(f"failed to generate thumbnail prompt: {e}")

    return f"Professional YouTube thumbnail for video about {video_subject}, vibrant colors, 16:9 aspect ratio"


def generate_thumbnail_with_api(
    image_prompt: str,
    output_path: str,
    api_provider: str = "openai",
) -> str:
    if api_provider == "openai":
        return _generate_with_openai(image_prompt, output_path)
    raise ValueError(f"Unsupported thumbnail API provider: {api_provider}")


def _generate_with_openai(image_prompt: str, output_path: str) -> str:
    api_key = config.app.get("openai_api_key", "")
    if not api_key:
        raise ValueError("OpenAI API key not configured for thumbnail generation")

    base_url = config.app.get("openai_base_url", "https://api.openai.com/v1")
    base_url = base_url.rstrip("/")

    try:
        resp = requests.post(
            f"{base_url}/images/generations",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": "dall-e-3",
                "prompt": image_prompt,
                "n": 1,
                "size": "1792x1024",
                "quality": "standard",
            },
            timeout=120,
        )
        resp.raise_for_status()
        data = resp.json()
        image_url = data["data"][0]["url"]

        img_resp = requests.get(image_url, timeout=60)
        img_resp.raise_for_status()

        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        with open(output_path, "wb") as f:
            f.write(img_resp.content)

        logger.success(f"thumbnail generated: {output_path}")
        return output_path

    except Exception as e:
        raise ValueError(f"OpenAI image generation failed: {e}")


def generate_thumbnail_simple(
    title_text: str,
    output_path: str,
    bg_color: str = "#1a1a2e",
    text_color: str = "#ffffff",
    accent_color: str = "#e94560",
    width: int = 1280,
    height: int = 720,
) -> str:
    try:
        from PIL import Image, ImageDraw, ImageFont
    except ImportError:
        raise ValueError("Pillow is required for simple thumbnail generation. Install with: pip install Pillow")

    img = Image.new("RGB", (width, height), bg_color)
    draw = ImageDraw.Draw(img)

    bar_height = 8
    draw.rectangle([0, height - bar_height, width, height], fill=accent_color)
    draw.rectangle([0, 0, width, bar_height], fill=accent_color)

    font_size = 64
    font = None
    font_candidates = [
        os.path.join(utils.font_dir(), "NotoSansKR-Bold.ttf"),
        os.path.join(utils.font_dir(), "STHeitiMedium.ttc"),
        os.path.join(utils.font_dir(), "MicrosoftYaHeiBold.ttc"),
    ]
    for font_path in font_candidates:
        if os.path.exists(font_path):
            try:
                font = ImageFont.truetype(font_path, font_size)
                break
            except Exception:
                continue

    if font is None:
        try:
            font = ImageFont.truetype("arial.ttf", font_size)
        except Exception:
            font = ImageFont.load_default()

    max_chars_per_line = 18
    lines = []
    current_line = ""
    for char in title_text:
        current_line += char
        if len(current_line) >= max_chars_per_line:
            lines.append(current_line)
            current_line = ""
    if current_line:
        lines.append(current_line)

    lines = lines[:3]

    line_height = font_size + 20
    total_text_height = len(lines) * line_height
    y_start = (height - total_text_height) // 2

    for i, line in enumerate(lines):
        bbox = draw.textbbox((0, 0), line, font=font)
        text_width = bbox[2] - bbox[0]
        x = (width - text_width) // 2
        y = y_start + i * line_height

        for offset_x, offset_y in [(-2, -2), (-2, 2), (2, -2), (2, 2)]:
            draw.text((x + offset_x, y + offset_y), line, font=font, fill="#000000")

        draw.text((x, y), line, font=font, fill=text_color)

    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    img.save(output_path, "PNG", quality=95)
    logger.success(f"simple thumbnail generated: {output_path}")
    return output_path


def generate_for_task(
    task_id: str,
    video_subject: str,
    title_text: str = "",
    use_ai: bool = False,
) -> str:
    task_dir = utils.task_dir(task_id)
    output_path = os.path.join(task_dir, "thumbnail.png")

    display_text = title_text or video_subject

    if use_ai:
        try:
            image_prompt = generate_thumbnail_prompt(video_subject, display_text)
            return generate_thumbnail_with_api(image_prompt, output_path)
        except Exception as e:
            logger.warning(f"AI thumbnail failed, falling back to simple: {e}")

    return generate_thumbnail_simple(display_text, output_path)
