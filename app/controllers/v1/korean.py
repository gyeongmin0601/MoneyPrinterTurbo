from fastapi import Request

from app.controllers.v1.base import new_router
from app.services import korean_preset
from app.utils import utils

router = new_router()


@router.get(
    "/korean/voices",
    summary="List all Korean TTS voice presets",
)
def get_korean_voices():
    voices = korean_preset.get_all_korean_voices()
    return utils.get_response(200, {"voices": voices})


@router.get(
    "/korean/defaults",
    summary="Get Korean video defaults for a speech style",
)
def get_korean_defaults(speech_style: str = "friendly"):
    defaults = korean_preset.get_korean_defaults(speech_style)
    return utils.get_response(200, defaults)


@router.post(
    "/korean/detect-language",
    summary="Detect language of text and suggest voice/font",
)
def detect_and_suggest(request: Request, body: dict):
    text = body.get("text", "")
    language = korean_preset.detect_language(text)
    result = {"language": language}
    if language == "ko":
        result["suggested_defaults"] = korean_preset.get_korean_defaults()
    return utils.get_response(200, result)
