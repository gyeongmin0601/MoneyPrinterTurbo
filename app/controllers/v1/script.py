from fastapi import Request

from app.controllers.v1.base import new_router
from app.models.schema import (
    KoreanScriptRequest,
    KoreanScriptResponse,
    ScriptFromTopicRequest,
    ScriptReviewRequest,
    ScriptReviewResponse,
)
from app.services import script
from app.utils import utils

router = new_router()


@router.post(
    "/scripts/korean",
    response_model=KoreanScriptResponse,
    summary="Generate a structured Korean YouTube script",
)
def generate_korean_script(request: Request, body: KoreanScriptRequest):
    result = script.generate_korean_script(
        video_subject=body.video_subject,
        script_length=body.script_length,
        speech_style=body.speech_style,
        niche=body.niche,
        target_audience=body.target_audience,
        keywords=body.keywords,
        include_visual_cues=body.include_visual_cues,
    )
    return utils.get_response(200, result)


@router.post(
    "/scripts/korean/from-topic",
    response_model=KoreanScriptResponse,
    summary="Generate a Korean script from a trend-suggested topic",
)
def generate_from_topic(request: Request, body: ScriptFromTopicRequest):
    topic = {
        "title": body.title,
        "title_ko": body.title_ko,
        "description": body.description,
        "description_ko": body.description_ko,
        "keywords": body.keywords,
    }
    result = script.generate_from_topic(
        topic=topic,
        script_length=body.script_length,
        speech_style=body.speech_style,
    )
    return utils.get_response(200, result)


@router.post(
    "/scripts/review",
    response_model=ScriptReviewResponse,
    summary="Review and score a script for quality",
)
def review_script(request: Request, body: ScriptReviewRequest):
    result = script.review_script(script_text=body.script_text)
    return utils.get_response(200, result)
