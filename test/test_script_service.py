import json
import sys
from unittest.mock import MagicMock, patch

import pytest

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

from app.services import script
from app.services.script import ScriptLength, SpeechStyle


class TestScriptLength:
    def test_length_values(self):
        assert ScriptLength.SHORT == "short"
        assert ScriptLength.MEDIUM == "medium"
        assert ScriptLength.LONG == "long"


class TestSpeechStyle:
    def test_style_values(self):
        assert SpeechStyle.FORMAL == "formal"
        assert SpeechStyle.FRIENDLY == "friendly"
        assert SpeechStyle.CASUAL == "casual"


class TestGenerateKoreanScript:
    @patch("app.services.script.llm")
    def test_successful_generation(self, mock_llm):
        mock_response = json.dumps({
            "hook": "여러분, 이거 아시나요?",
            "context": "많은 분들이 모르는 사실인데요.",
            "sections": [
                {"content": "첫 번째 포인트는...", "visual_cue": "chart showing data"},
                {"content": "두 번째로...", "visual_cue": "person working"},
            ],
            "engagement": "여러분은 어떻게 생각하세요?",
            "conclusion": "오늘 내용이 도움이 됐다면 구독 부탁드려요.",
            "full_script": "여러분, 이거 아시나요? 많은 분들이 모르는 사실인데요. 첫 번째 포인트는... 두 번째로... 여러분은 어떻게 생각하세요? 오늘 내용이 도움이 됐다면 구독 부탁드려요.",
            "estimated_duration_seconds": 360,
            "search_terms": ["money tips", "saving money"],
        })
        mock_llm._generate_response.return_value = mock_response

        result = script.generate_korean_script("돈 아끼는 방법")

        assert result["full_script"] != ""
        assert result["hook"] == "여러분, 이거 아시나요?"
        assert len(result["sections"]) == 2
        assert result["estimated_duration_seconds"] == 360
        assert result["script_length"] == "medium"
        assert result["speech_style"] == "friendly"

    @patch("app.services.script.llm")
    def test_json_in_markdown_codeblock(self, mock_llm):
        mock_response = '```json\n' + json.dumps({
            "hook": "테스트 훅",
            "context": "테스트 컨텍스트",
            "sections": [],
            "engagement": "",
            "conclusion": "",
            "full_script": "테스트 대본 전체",
            "estimated_duration_seconds": 60,
            "search_terms": [],
        }) + '\n```'
        mock_llm._generate_response.return_value = mock_response

        result = script.generate_korean_script("테스트 주제")
        assert result["full_script"] == "테스트 대본 전체"

    @patch("app.services.script.llm")
    def test_fallback_on_invalid_json(self, mock_llm):
        mock_llm._generate_response.return_value = "이것은 유효하지 않은 JSON입니다. 대본 내용만 있습니다."

        result = script.generate_korean_script("테스트 주제")
        assert result["full_script"] != ""
        assert result["sections"] == []

    @patch("app.services.script.llm")
    def test_with_all_options(self, mock_llm):
        mock_response = json.dumps({
            "hook": "훅",
            "context": "컨텍스트",
            "sections": [{"content": "내용", "visual_cue": "visual"}],
            "engagement": "참여",
            "conclusion": "결론",
            "full_script": "전체 대본",
            "estimated_duration_seconds": 120,
            "search_terms": ["test"],
        })
        mock_llm._generate_response.return_value = mock_response

        result = script.generate_korean_script(
            video_subject="AI 트렌드",
            script_length=ScriptLength.SHORT,
            speech_style=SpeechStyle.FORMAL,
            niche="technology",
            target_audience="개발자",
            keywords=["AI", "인공지능"],
            include_visual_cues=True,
        )
        assert result["script_length"] == "short"
        assert result["speech_style"] == "formal"

    @patch("app.services.script.llm")
    def test_error_response_retries(self, mock_llm):
        mock_llm._generate_response.side_effect = [
            "Error: API key invalid",
            "Error: rate limited",
            "Error: timeout",
            # fallback calls _generate_response 3 more times
            "폴백 대본 내용입니다. 테스트를 위한 텍스트.",
            "",
            "",
        ]

        result = script.generate_korean_script("테스트")
        assert result["full_script"] == "폴백 대본 내용입니다. 테스트를 위한 텍스트."


class TestReviewScript:
    @patch("app.services.script.llm")
    def test_successful_review(self, mock_llm):
        mock_response = json.dumps({
            "hook_strength": 8,
            "information_density": 7,
            "engagement": 6,
            "pacing": 8,
            "retention": 7,
            "overall_score": 7.2,
            "improvements": ["Add more examples"],
            "improvements_ko": ["예시를 더 추가하세요"],
        })
        mock_llm._generate_response.return_value = mock_response

        result = script.review_script("테스트 대본입니다.")
        assert result["overall_score"] == 7.2
        assert result["hook_strength"] == 8
        assert len(result["improvements"]) == 1

    @patch("app.services.script.llm")
    def test_review_failure_returns_default(self, mock_llm):
        mock_llm._generate_response.return_value = "invalid response"

        result = script.review_script("테스트 대본")
        assert result["overall_score"] == 0
        assert "Review failed" in result["improvements"][0]


class TestGenerateFromTopic:
    @patch("app.services.script.llm")
    def test_from_topic(self, mock_llm):
        mock_response = json.dumps({
            "hook": "훅",
            "context": "컨텍스트",
            "sections": [],
            "engagement": "",
            "conclusion": "",
            "full_script": "주제 기반 대본",
            "estimated_duration_seconds": 300,
            "search_terms": [],
        })
        mock_llm._generate_response.return_value = mock_response

        topic = {
            "title": "Budget Travel Tips",
            "title_ko": "알뜰 여행 팁",
            "description": "Save money while traveling",
            "description_ko": "여행하면서 돈 아끼는 법",
            "keywords": ["travel", "budget", "tips"],
        }
        result = script.generate_from_topic(topic)
        assert result["full_script"] == "주제 기반 대본"
        assert result["video_subject"] == "알뜰 여행 팁 - 여행하면서 돈 아끼는 법"

    @patch("app.services.script.llm")
    def test_from_topic_english_fallback(self, mock_llm):
        mock_response = json.dumps({
            "hook": "hook",
            "context": "ctx",
            "sections": [],
            "engagement": "",
            "conclusion": "",
            "full_script": "script",
            "estimated_duration_seconds": 300,
            "search_terms": [],
        })
        mock_llm._generate_response.return_value = mock_response

        topic = {
            "title": "AI Trends",
            "title_ko": "",
            "description": "Latest AI developments",
            "description_ko": "",
            "keywords": ["AI"],
        }
        result = script.generate_from_topic(topic)
        assert result["video_subject"] == "AI Trends - Latest AI developments"
