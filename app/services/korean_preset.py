"""
Korean-specific presets for TTS voices, fonts, and video defaults.

Provides recommended configurations for Korean YouTube content creation
and a helper to auto-detect language and apply appropriate defaults.
"""

from typing import Optional

from loguru import logger


# ──────────────────────────────────────────────────────────────────
# Korean Edge TTS Voice Presets
# ──────────────────────────────────────────────────────────────────

KOREAN_VOICES = {
    "sunhi": {
        "voice_name": "ko-KR-SunHiNeural-Female",
        "gender": "Female",
        "description": "밝고 친근한 여성 음성 (뉴스, 해설, 일상)",
        "recommended_for": ["friendly", "casual"],
        "sample_rate": 1.0,
    },
    "injoon": {
        "voice_name": "ko-KR-InJoonNeural-Male",
        "gender": "Male",
        "description": "차분하고 신뢰감 있는 남성 음성 (교육, 다큐, 경제)",
        "recommended_for": ["formal", "friendly"],
        "sample_rate": 1.0,
    },
    "hyunsu": {
        "voice_name": "ko-KR-HyunsuMultilingualNeural-Male",
        "gender": "Male",
        "description": "자연스러운 다국어 남성 음성 (IT, 글로벌 주제)",
        "recommended_for": ["formal", "friendly"],
        "sample_rate": 1.0,
    },
}

DEFAULT_VOICE_BY_STYLE = {
    "formal": "injoon",
    "friendly": "sunhi",
    "casual": "sunhi",
}


# ──────────────────────────────────────────────────────────────────
# Korean Font Presets
# ──────────────────────────────────────────────────────────────────

KOREAN_FONTS = {
    "noto_sans_kr": {
        "file_name": "NotoSansKR-Bold.ttf",
        "display_name": "Noto Sans KR Bold",
        "description": "구글 노토 산스 한국어 - 가장 보편적인 한국어 자막 폰트",
        "recommended": True,
        "download_url": "https://fonts.google.com/noto/specimen/Noto+Sans+KR",
    },
    "nanum_gothic": {
        "file_name": "NanumGothicBold.ttf",
        "display_name": "나눔고딕 Bold",
        "description": "네이버 나눔고딕 - 깔끔하고 가독성 높은 폰트",
        "recommended": False,
        "download_url": "https://hangeul.naver.com/font",
    },
}

DEFAULT_KOREAN_FONT = "NotoSansKR-Bold.ttf"
FALLBACK_FONT = "STHeitiMedium.ttc"  # CJK font already in project


# ──────────────────────────────────────────────────────────────────
# Korean Video Defaults
# ──────────────────────────────────────────────────────────────────

KOREAN_VIDEO_DEFAULTS = {
    "voice_name": "ko-KR-SunHiNeural-Female",
    "voice_rate": 1.05,  # slightly faster for Korean YouTube style
    "voice_volume": 1.0,
    "bgm_volume": 0.15,
    "font_name": DEFAULT_KOREAN_FONT,
    "font_size": 58,
    "text_fore_color": "#FFFFFF",
    "stroke_color": "#000000",
    "stroke_width": 2.0,
    "subtitle_position": "bottom",
    "video_language": "ko",
}


# ──────────────────────────────────────────────────────────────────
# Helper Functions
# ──────────────────────────────────────────────────────────────────

def get_voice_preset(style: str = "friendly") -> dict:
    preset_key = DEFAULT_VOICE_BY_STYLE.get(style, "sunhi")
    preset = KOREAN_VOICES[preset_key]
    return {
        "voice_name": preset["voice_name"],
        "voice_rate": preset["sample_rate"],
    }


def get_all_korean_voices() -> list:
    return [
        {
            "key": key,
            "voice_name": v["voice_name"],
            "gender": v["gender"],
            "description": v["description"],
            "recommended_for": v["recommended_for"],
        }
        for key, v in KOREAN_VOICES.items()
    ]


def get_korean_defaults(speech_style: str = "friendly") -> dict:
    voice = get_voice_preset(speech_style)
    defaults = {**KOREAN_VIDEO_DEFAULTS}
    defaults["voice_name"] = voice["voice_name"]
    defaults["voice_rate"] = voice["voice_rate"]
    return defaults


def detect_language(text: str) -> str:
    if not text:
        return "en"
    korean_count = sum(1 for c in text if '\uac00' <= c <= '\ud7a3')
    total_alpha = sum(1 for c in text if c.isalpha())
    if total_alpha == 0:
        return "en"
    if korean_count / total_alpha > 0.3:
        return "ko"
    chinese_count = sum(1 for c in text if '\u4e00' <= c <= '\u9fff')
    if chinese_count / total_alpha > 0.3:
        return "zh"
    return "en"


def apply_korean_defaults_if_needed(params: dict) -> dict:
    text = params.get("video_subject", "") or params.get("video_script", "")
    language = params.get("video_language", "")

    if not language:
        language = detect_language(text)

    if language != "ko":
        return params

    defaults = get_korean_defaults()
    result = {**params}

    if not result.get("voice_name"):
        result["voice_name"] = defaults["voice_name"]
        logger.info(f"auto-applied Korean voice: {defaults['voice_name']}")

    if not result.get("font_name") or result["font_name"] == "STHeitiMedium.ttc":
        result["font_name"] = defaults["font_name"]
        logger.info(f"auto-applied Korean font: {defaults['font_name']}")

    if not result.get("video_language"):
        result["video_language"] = "ko"

    return result
