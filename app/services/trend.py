import json
import re
import time
from datetime import datetime, date
from typing import List, Optional

import requests
from loguru import logger

from app.config import config
from app.services import llm

_YOUTUBE_API_BASE = "https://www.googleapis.com/youtube/v3"

_QUOTA_COSTS = {
    "videos.list": 1,
    "search.list": 100,
}

_quota_usage = {
    "date": "",
    "used": 0,
}

_cache = {}

_CACHE_TTL_TRENDING = 1800  # 30 minutes
_CACHE_TTL_KEYWORD = 3600  # 1 hour


def _get_api_key() -> str:
    api_key = config.app.get("youtube_api_key", "")
    if not api_key:
        raise ValueError(
            "YouTube API key is not configured. "
            "Set 'youtube_api_key' in config.toml"
        )
    return api_key


def _check_quota(cost: int) -> bool:
    today = date.today().isoformat()
    if _quota_usage["date"] != today:
        _quota_usage["date"] = today
        _quota_usage["used"] = 0

    limit = config.app.get("youtube_quota_daily_limit", 10000)
    reserved = config.app.get("youtube_quota_reserved", 2000)
    available = limit - reserved - _quota_usage["used"]

    if cost > available:
        logger.warning(
            f"YouTube API quota insufficient. "
            f"used: {_quota_usage['used']}, needed: {cost}, available: {available}"
        )
        return False
    return True


def _record_quota(cost: int):
    today = date.today().isoformat()
    if _quota_usage["date"] != today:
        _quota_usage["date"] = today
        _quota_usage["used"] = 0
    _quota_usage["used"] += cost
    logger.debug(f"YouTube API quota used: {_quota_usage['used']} (+{cost})")


def _get_cache(key: str):
    if key in _cache:
        entry = _cache[key]
        if time.time() < entry["expires_at"]:
            logger.debug(f"cache hit: {key}")
            return entry["data"]
        del _cache[key]
    return None


def _set_cache(key: str, data, ttl: int):
    _cache[key] = {
        "data": data,
        "expires_at": time.time() + ttl,
    }


def _make_request(endpoint: str, params: dict) -> dict:
    api_key = _get_api_key()
    params["key"] = api_key

    url = f"{_YOUTUBE_API_BASE}/{endpoint}"

    proxies = {}
    http_proxy = config.proxy.get("http", "")
    https_proxy = config.proxy.get("https", "")
    if http_proxy:
        proxies["http"] = http_proxy
    if https_proxy:
        proxies["https"] = https_proxy

    try:
        resp = requests.get(url, params=params, proxies=proxies or None, timeout=30)
        resp.raise_for_status()
        return resp.json()
    except requests.exceptions.HTTPError as e:
        if resp.status_code == 403:
            error_reason = ""
            try:
                error_data = resp.json()
                error_reason = error_data.get("error", {}).get("errors", [{}])[0].get("reason", "")
            except Exception:
                pass
            if error_reason == "quotaExceeded":
                raise ValueError("YouTube API daily quota exceeded")
            raise ValueError(f"YouTube API forbidden: {error_reason or str(e)}")
        raise ValueError(f"YouTube API error ({resp.status_code}): {str(e)}")
    except requests.exceptions.RequestException as e:
        raise ValueError(f"YouTube API request failed: {str(e)}")


def _parse_video(item: dict) -> dict:
    snippet = item.get("snippet", {})
    statistics = item.get("statistics", {})
    thumbnails = snippet.get("thumbnails", {})
    thumbnail_url = (
        thumbnails.get("high", {}).get("url", "")
        or thumbnails.get("medium", {}).get("url", "")
        or thumbnails.get("default", {}).get("url", "")
    )
    return {
        "video_id": item.get("id", ""),
        "title": snippet.get("title", ""),
        "channel_title": snippet.get("channelTitle", ""),
        "published_at": snippet.get("publishedAt", ""),
        "view_count": int(statistics.get("viewCount", 0)),
        "like_count": int(statistics.get("likeCount", 0)),
        "comment_count": int(statistics.get("commentCount", 0)),
        "category_id": snippet.get("categoryId", ""),
        "tags": snippet.get("tags", []),
        "thumbnail_url": thumbnail_url,
    }


def fetch_trending(
    region_code: str = "KR",
    category_id: Optional[str] = None,
    max_results: int = 20,
) -> List[dict]:
    cache_key = f"trending:{region_code}:{category_id}"
    cached = _get_cache(cache_key)
    if cached is not None:
        return cached

    cost = _QUOTA_COSTS["videos.list"]
    if not _check_quota(cost):
        raise ValueError("Insufficient YouTube API quota for trending request")

    params = {
        "part": "snippet,statistics",
        "chart": "mostPopular",
        "regionCode": region_code,
        "maxResults": min(max_results, 50),
    }
    if category_id:
        params["videoCategoryId"] = category_id

    data = _make_request("videos", params)
    _record_quota(cost)

    videos = [_parse_video(item) for item in data.get("items", [])]
    _set_cache(cache_key, videos, _CACHE_TTL_TRENDING)

    logger.success(f"fetched {len(videos)} trending videos for {region_code}")
    return videos


def _fetch_video_statistics(video_ids: List[str]) -> dict:
    if not video_ids:
        return {}

    cost = _QUOTA_COSTS["videos.list"]
    if not _check_quota(cost):
        raise ValueError("Insufficient YouTube API quota for video statistics")

    params = {
        "part": "snippet,statistics",
        "id": ",".join(video_ids[:50]),
    }
    data = _make_request("videos", params)
    _record_quota(cost)

    result = {}
    for item in data.get("items", []):
        result[item["id"]] = _parse_video(item)
    return result


def _search_videos(
    keyword: str,
    region_code: str = "KR",
    language: str = "ko",
    max_results: int = 10,
    order: str = "relevance",
) -> dict:
    cost = _QUOTA_COSTS["search.list"]
    if not _check_quota(cost):
        raise ValueError("Insufficient YouTube API quota for search request")

    params = {
        "part": "snippet",
        "type": "video",
        "q": keyword,
        "regionCode": region_code,
        "relevanceLanguage": language,
        "order": order,
        "maxResults": min(max_results, 25),
    }
    data = _make_request("search", params)
    _record_quota(cost)

    total_results = data.get("pageInfo", {}).get("totalResults", 0)
    video_ids = [
        item["id"]["videoId"]
        for item in data.get("items", [])
        if item.get("id", {}).get("videoId")
    ]

    return {
        "total_results": total_results,
        "video_ids": video_ids,
    }


def _calculate_engagement_rate(
    view_count: int, like_count: int, comment_count: int
) -> float:
    if view_count <= 0:
        return 0.0
    return round((like_count + comment_count) / view_count * 100, 2)


def _assess_competition(total_results: int, avg_view_count: float) -> str:
    if total_results > 1_000_000 and avg_view_count > 100_000:
        return "high"
    if total_results < 100_000 and avg_view_count < 10_000:
        return "low"
    return "medium"


def analyze_keyword(
    keyword: str,
    region_code: str = "KR",
    language: str = "ko",
    max_results: int = 10,
    order: str = "relevance",
) -> dict:
    cache_key = f"keyword:{keyword}:{region_code}:{order}"
    cached = _get_cache(cache_key)
    if cached is not None:
        return cached

    search_data = _search_videos(keyword, region_code, language, max_results, order)
    total_results = search_data["total_results"]
    video_ids = search_data["video_ids"]

    videos_map = _fetch_video_statistics(video_ids)
    videos = list(videos_map.values())

    if videos:
        avg_views = sum(v["view_count"] for v in videos) / len(videos)
        avg_likes = sum(v["like_count"] for v in videos) / len(videos)
        avg_comments = sum(v["comment_count"] for v in videos) / len(videos)
    else:
        avg_views = avg_likes = avg_comments = 0.0

    engagement = _calculate_engagement_rate(
        int(avg_views), int(avg_likes), int(avg_comments)
    )
    competition = _assess_competition(total_results, avg_views)

    result = {
        "keyword": keyword,
        "total_results": total_results,
        "avg_view_count": round(avg_views, 1),
        "avg_like_count": round(avg_likes, 1),
        "avg_comment_count": round(avg_comments, 1),
        "engagement_rate": engagement,
        "top_videos": videos,
        "competition_level": competition,
    }

    _set_cache(cache_key, result, _CACHE_TTL_KEYWORD)
    logger.success(
        f"analyzed keyword '{keyword}': "
        f"results={total_results}, avg_views={avg_views:.0f}, "
        f"competition={competition}"
    )
    return result


def suggest_topics(
    region_code: str = "KR",
    category_id: Optional[str] = None,
    language: str = "ko",
    num_suggestions: int = 5,
    niche: Optional[str] = None,
) -> dict:
    trending = fetch_trending(region_code, category_id, max_results=20)

    trending_summary = []
    for v in trending[:15]:
        trending_summary.append(
            f"- \"{v['title']}\" (views: {v['view_count']:,}, "
            f"likes: {v['like_count']:,}, channel: {v['channel_title']})"
        )
    trending_text = "\n".join(trending_summary)

    keyword_context = ""
    keyword_metrics = None
    if niche:
        try:
            keyword_metrics = analyze_keyword(niche, region_code, language, max_results=10)
            keyword_context = f"""
### Niche Keyword Analysis: "{niche}"
- Total search results: {keyword_metrics['total_results']:,}
- Average views: {keyword_metrics['avg_view_count']:,.0f}
- Average likes: {keyword_metrics['avg_like_count']:,.0f}
- Engagement rate: {keyword_metrics['engagement_rate']}%
- Competition level: {keyword_metrics['competition_level']}
"""
        except Exception as e:
            logger.warning(f"failed to analyze niche keyword '{niche}': {e}")

    region_context = ""
    if region_code == "KR":
        region_context = """
### Market Context
- Target: Korean YouTube market (한국 유튜브 시장)
- Audience: Korean-speaking viewers
- Consider: Korean cultural trends, K-pop, Korean economy, Korean lifestyle
- Script style: 해요체 or 합니다체 depending on topic formality
"""

    prompt = f"""
# Role: YouTube Content Strategy Analyst

## Task
Analyze the following YouTube trending data and suggest {num_suggestions} specific video topics
with high potential for views and engagement.

## Trending Videos ({region_code})
{trending_text}

{keyword_context}
{region_context}

## Output Requirements
Return a JSON array of topic suggestions. Each topic must have these fields:
- "title": English title
- "title_ko": Korean title (한국어 제목)
- "description": Brief description in English (1-2 sentences)
- "description_ko": Brief description in Korean (1-2 sentences)
- "keywords": Array of 3-5 search keywords in English
- "demand_score": 0-100 (estimated demand based on trend data)
- "competition_score": 0-100 (estimated competition level)
- "opportunity_score": 0-100 (calculated as: demand - competition * 0.7, clamped 0-100)
- "reasoning": Why this topic has potential (English)
- "reasoning_ko": Why this topic has potential (Korean)

## Constraints
1. Return ONLY a valid JSON array. No other text.
2. Topics should be specific and actionable, not generic.
3. Each topic should be different from the trending videos but inspired by the trends.
4. Focus on gaps and underserved angles in the trending topics.
5. Scoring must be realistic and justified.

## Output Example
[{{"title": "Example Topic", "title_ko": "예시 주제", "description": "...", "description_ko": "...", "keywords": ["keyword1", "keyword2"], "demand_score": 75, "competition_score": 45, "opportunity_score": 43.5, "reasoning": "...", "reasoning_ko": "..."}}]
""".strip()

    logger.info(f"generating topic suggestions for {region_code}, niche={niche}")

    topics = []
    response = ""
    for i in range(3):
        try:
            response = llm._generate_response(prompt)
            if "Error: " in response:
                logger.error(f"LLM error: {response}")
                continue

            topics = json.loads(response)
            if isinstance(topics, list) and len(topics) > 0:
                break
        except json.JSONDecodeError:
            if response:
                match = re.search(r"\[.*]", response, re.DOTALL)
                if match:
                    try:
                        topics = json.loads(match.group())
                        if isinstance(topics, list) and len(topics) > 0:
                            break
                    except json.JSONDecodeError:
                        pass
            logger.warning(f"failed to parse LLM response, attempt {i + 1}/3")

    validated_topics = []
    for t in topics:
        if not isinstance(t, dict):
            continue
        validated_topics.append({
            "title": t.get("title", ""),
            "title_ko": t.get("title_ko", ""),
            "description": t.get("description", ""),
            "description_ko": t.get("description_ko", ""),
            "keywords": t.get("keywords", []),
            "demand_score": float(t.get("demand_score", 0)),
            "competition_score": float(t.get("competition_score", 0)),
            "opportunity_score": float(t.get("opportunity_score", 0)),
            "reasoning": t.get("reasoning", ""),
            "reasoning_ko": t.get("reasoning_ko", ""),
        })

    validated_topics.sort(key=lambda x: x["opportunity_score"], reverse=True)

    summary = f"Generated {len(validated_topics)} topic suggestions from {len(trending)} trending videos"
    summary_ko = f"{len(trending)}개 트렌딩 영상에서 {len(validated_topics)}개 주제를 생성했습니다"

    if niche and keyword_metrics:
        summary += f" with niche focus on '{niche}' (competition: {keyword_metrics['competition_level']})"
        summary_ko += f" (니치: '{niche}', 경쟁도: {keyword_metrics['competition_level']})"

    logger.success(f"suggested {len(validated_topics)} topics")

    return {
        "topics": validated_topics,
        "analysis_summary": summary,
        "analysis_summary_ko": summary_ko,
    }


def get_quota_status() -> dict:
    today = date.today().isoformat()
    if _quota_usage["date"] != today:
        used = 0
    else:
        used = _quota_usage["used"]

    limit = config.app.get("youtube_quota_daily_limit", 10000)
    reserved = config.app.get("youtube_quota_reserved", 2000)

    return {
        "date": today,
        "used": used,
        "limit": limit,
        "reserved": reserved,
        "available": max(0, limit - reserved - used),
    }
