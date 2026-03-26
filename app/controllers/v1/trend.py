from fastapi import Request

from app.controllers.v1.base import new_router
from app.models.schema import (
    KeywordAnalysisRequest,
    KeywordAnalysisResponse,
    TopicSuggestionRequest,
    TopicSuggestionResponse,
    TrendingRequest,
    TrendingResponse,
)
from app.services import trend
from app.utils import utils

router = new_router()


@router.get(
    "/trends",
    response_model=TrendingResponse,
    summary="Fetch YouTube trending videos by region",
)
def get_trending(
    region_code: str = "KR",
    category_id: str = None,
    max_results: int = 20,
):
    videos = trend.fetch_trending(
        region_code=region_code,
        category_id=category_id,
        max_results=max_results,
    )
    from datetime import datetime

    response = {
        "videos": videos,
        "region_code": region_code,
        "fetched_at": datetime.now().isoformat(),
    }
    return utils.get_response(200, response)


@router.post(
    "/trends/analyze",
    response_model=KeywordAnalysisResponse,
    summary="Analyze keyword competition and engagement",
)
def analyze_keyword(request: Request, body: KeywordAnalysisRequest):
    metrics = trend.analyze_keyword(
        keyword=body.keyword,
        region_code=body.region_code,
        language=body.language,
        max_results=body.max_results,
        order=body.order,
    )
    return utils.get_response(200, metrics)


@router.post(
    "/trends/suggest",
    response_model=TopicSuggestionResponse,
    summary="Get AI-suggested video topics based on trends",
)
def suggest_topics(request: Request, body: TopicSuggestionRequest):
    result = trend.suggest_topics(
        region_code=body.region_code,
        category_id=body.category_id,
        language=body.language,
        num_suggestions=body.num_suggestions,
        niche=body.niche,
    )
    return utils.get_response(200, result)


@router.get(
    "/trends/quota",
    summary="Check YouTube API quota usage",
)
def get_quota():
    quota = trend.get_quota_status()
    return utils.get_response(200, quota)
