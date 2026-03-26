import json
import sys
import time
from unittest.mock import MagicMock, patch

import pytest

# Mock heavy dependencies before importing trend
sys.modules["g4f"] = MagicMock()
sys.modules["openai"] = MagicMock()
sys.modules["openai.types"] = MagicMock()
sys.modules["openai.types.chat"] = MagicMock()
sys.modules["dashscope"] = MagicMock()
sys.modules["azure"] = MagicMock()
sys.modules["azure.cognitiveservices"] = MagicMock()
sys.modules["azure.cognitiveservices.speech"] = MagicMock()
sys.modules["google"] = MagicMock()
sys.modules["google.generativeai"] = MagicMock()

from app.services import trend


class TestEngagementRate:
    def test_normal_case(self):
        rate = trend._calculate_engagement_rate(100_000, 5_000, 500)
        assert rate == 5.5

    def test_zero_views(self):
        rate = trend._calculate_engagement_rate(0, 100, 10)
        assert rate == 0.0

    def test_no_engagement(self):
        rate = trend._calculate_engagement_rate(100_000, 0, 0)
        assert rate == 0.0


class TestCompetitionAssessment:
    def test_high_competition(self):
        assert trend._assess_competition(2_000_000, 200_000) == "high"

    def test_low_competition(self):
        assert trend._assess_competition(50_000, 5_000) == "low"

    def test_medium_competition(self):
        assert trend._assess_competition(500_000, 50_000) == "medium"

    def test_borderline_high_results_low_views(self):
        assert trend._assess_competition(2_000_000, 5_000) == "medium"

    def test_borderline_low_results_high_views(self):
        assert trend._assess_competition(50_000, 200_000) == "medium"


class TestCache:
    def setup_method(self):
        trend._cache.clear()

    def test_set_and_get(self):
        trend._set_cache("test_key", {"data": 123}, 60)
        result = trend._get_cache("test_key")
        assert result == {"data": 123}

    def test_expired(self):
        trend._set_cache("test_key", {"data": 123}, 0)
        time.sleep(0.01)
        result = trend._get_cache("test_key")
        assert result is None

    def test_miss(self):
        result = trend._get_cache("nonexistent")
        assert result is None


class TestQuota:
    def setup_method(self):
        trend._quota_usage["date"] = ""
        trend._quota_usage["used"] = 0

    @patch("app.services.trend.config")
    def test_check_quota_available(self, mock_config):
        mock_config.app = MagicMock()
        mock_config.app.get = MagicMock(side_effect=lambda k, d=None: {"youtube_quota_daily_limit": 10000, "youtube_quota_reserved": 2000}.get(k, d))
        assert trend._check_quota(100) is True

    @patch("app.services.trend.config")
    def test_check_quota_exceeded(self, mock_config):
        mock_config.app = MagicMock()
        mock_config.app.get = MagicMock(side_effect=lambda k, d=None: {"youtube_quota_daily_limit": 10000, "youtube_quota_reserved": 2000}.get(k, d))
        trend._quota_usage["date"] = trend.date.today().isoformat()
        trend._quota_usage["used"] = 9000
        assert trend._check_quota(100) is False

    def test_quota_status(self):
        trend._quota_usage["date"] = trend.date.today().isoformat()
        trend._quota_usage["used"] = 500
        with patch("app.services.trend.config") as mock_config:
            mock_config.app = MagicMock()
            mock_config.app.get = MagicMock(side_effect=lambda k, d=None: {"youtube_quota_daily_limit": 10000, "youtube_quota_reserved": 2000}.get(k, d))
            status = trend.get_quota_status()
        assert status["used"] == 500
        assert status["available"] == 7500


class TestParseVideo:
    def test_full_data(self):
        item = {
            "id": "abc123",
            "snippet": {
                "title": "Test Video",
                "channelTitle": "TestChannel",
                "publishedAt": "2026-03-26T10:00:00Z",
                "categoryId": "24",
                "tags": ["tag1", "tag2"],
                "thumbnails": {
                    "high": {"url": "https://example.com/thumb.jpg"},
                },
            },
            "statistics": {
                "viewCount": "150000",
                "likeCount": "5000",
                "commentCount": "300",
            },
        }
        result = trend._parse_video(item)
        assert result["video_id"] == "abc123"
        assert result["title"] == "Test Video"
        assert result["view_count"] == 150000
        assert result["like_count"] == 5000
        assert result["tags"] == ["tag1", "tag2"]

    def test_missing_statistics(self):
        item = {
            "id": "abc123",
            "snippet": {
                "title": "Test Video",
                "channelTitle": "TestChannel",
                "publishedAt": "2026-03-26T10:00:00Z",
                "thumbnails": {},
            },
        }
        result = trend._parse_video(item)
        assert result["view_count"] == 0
        assert result["like_count"] == 0
        assert result["tags"] == []


class TestFetchTrending:
    def setup_method(self):
        trend._cache.clear()
        trend._quota_usage["date"] = ""
        trend._quota_usage["used"] = 0

    @patch("app.services.trend._make_request")
    @patch("app.services.trend.config")
    def test_fetch_trending(self, mock_config, mock_request):
        mock_config.app = MagicMock()
        mock_config.app.get = MagicMock(side_effect=lambda k, d=None: {
            "youtube_quota_daily_limit": 10000,
            "youtube_quota_reserved": 2000,
        }.get(k, d))

        mock_request.return_value = {
            "items": [
                {
                    "id": "vid1",
                    "snippet": {
                        "title": "Trending Video 1",
                        "channelTitle": "Channel1",
                        "publishedAt": "2026-03-26T10:00:00Z",
                        "thumbnails": {"high": {"url": "https://example.com/1.jpg"}},
                        "tags": ["trend"],
                    },
                    "statistics": {
                        "viewCount": "1000000",
                        "likeCount": "50000",
                        "commentCount": "3000",
                    },
                }
            ]
        }

        videos = trend.fetch_trending("KR")
        assert len(videos) == 1
        assert videos[0]["title"] == "Trending Video 1"
        assert videos[0]["view_count"] == 1000000

    @patch("app.services.trend._make_request")
    @patch("app.services.trend.config")
    def test_fetch_trending_cached(self, mock_config, mock_request):
        mock_config.app = MagicMock()
        mock_config.app.get = MagicMock(side_effect=lambda k, d=None: {
            "youtube_quota_daily_limit": 10000,
            "youtube_quota_reserved": 2000,
        }.get(k, d))

        mock_request.return_value = {"items": []}

        trend.fetch_trending("US")
        trend.fetch_trending("US")
        assert mock_request.call_count == 1


class TestAnalyzeKeyword:
    def setup_method(self):
        trend._cache.clear()
        trend._quota_usage["date"] = ""
        trend._quota_usage["used"] = 0

    @patch("app.services.trend._fetch_video_statistics")
    @patch("app.services.trend._search_videos")
    @patch("app.services.trend.config")
    def test_analyze_keyword(self, mock_config, mock_search, mock_stats):
        mock_config.app = MagicMock()
        mock_config.app.get = MagicMock(side_effect=lambda k, d=None: {
            "youtube_quota_daily_limit": 10000,
            "youtube_quota_reserved": 2000,
        }.get(k, d))

        mock_search.return_value = {
            "total_results": 500000,
            "video_ids": ["vid1", "vid2"],
        }
        mock_stats.return_value = {
            "vid1": {
                "video_id": "vid1",
                "title": "Video 1",
                "channel_title": "Ch1",
                "published_at": "",
                "view_count": 100000,
                "like_count": 5000,
                "comment_count": 300,
                "category_id": "",
                "tags": [],
                "thumbnail_url": "",
            },
            "vid2": {
                "video_id": "vid2",
                "title": "Video 2",
                "channel_title": "Ch2",
                "published_at": "",
                "view_count": 200000,
                "like_count": 10000,
                "comment_count": 600,
                "category_id": "",
                "tags": [],
                "thumbnail_url": "",
            },
        }

        result = trend.analyze_keyword("python tutorial", "KR", "ko")
        assert result["keyword"] == "python tutorial"
        assert result["total_results"] == 500000
        assert result["avg_view_count"] == 150000.0
        assert result["competition_level"] == "medium"
        assert len(result["top_videos"]) == 2
