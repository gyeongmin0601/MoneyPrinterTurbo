import sys
from unittest.mock import MagicMock

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

from app.services import korean_preset


class TestDetectLanguage:
    def test_korean_text(self):
        assert korean_preset.detect_language("한국어 테스트입니다") == "ko"

    def test_english_text(self):
        assert korean_preset.detect_language("This is an English test") == "en"

    def test_chinese_text(self):
        assert korean_preset.detect_language("这是中文测试") == "zh"

    def test_mixed_korean_english(self):
        assert korean_preset.detect_language("오늘의 AI 트렌드를 알아보겠습니다") == "ko"

    def test_empty_string(self):
        assert korean_preset.detect_language("") == "en"

    def test_numbers_only(self):
        assert korean_preset.detect_language("12345") == "en"


class TestVoicePresets:
    def test_get_all_korean_voices(self):
        voices = korean_preset.get_all_korean_voices()
        assert len(voices) == 3
        keys = [v["key"] for v in voices]
        assert "sunhi" in keys
        assert "injoon" in keys
        assert "hyunsu" in keys

    def test_get_voice_preset_friendly(self):
        preset = korean_preset.get_voice_preset("friendly")
        assert "SunHi" in preset["voice_name"]

    def test_get_voice_preset_formal(self):
        preset = korean_preset.get_voice_preset("formal")
        assert "InJoon" in preset["voice_name"]

    def test_get_voice_preset_casual(self):
        preset = korean_preset.get_voice_preset("casual")
        assert "SunHi" in preset["voice_name"]

    def test_get_voice_preset_unknown_falls_back(self):
        preset = korean_preset.get_voice_preset("unknown_style")
        assert "SunHi" in preset["voice_name"]


class TestKoreanDefaults:
    def test_defaults_contain_required_keys(self):
        defaults = korean_preset.get_korean_defaults()
        assert "voice_name" in defaults
        assert "font_name" in defaults
        assert "video_language" in defaults
        assert defaults["video_language"] == "ko"

    def test_defaults_for_formal(self):
        defaults = korean_preset.get_korean_defaults("formal")
        assert "InJoon" in defaults["voice_name"]

    def test_defaults_for_friendly(self):
        defaults = korean_preset.get_korean_defaults("friendly")
        assert "SunHi" in defaults["voice_name"]


class TestApplyKoreanDefaults:
    def test_auto_detect_korean_and_apply(self):
        params = {
            "video_subject": "한국 경제 전망 분석",
            "voice_name": "",
            "font_name": "",
        }
        result = korean_preset.apply_korean_defaults_if_needed(params)
        assert "ko-KR" in result["voice_name"]
        assert result["video_language"] == "ko"

    def test_skip_for_english(self):
        params = {
            "video_subject": "Global economy trends",
            "voice_name": "",
            "font_name": "",
        }
        result = korean_preset.apply_korean_defaults_if_needed(params)
        assert result.get("voice_name") == ""

    def test_preserve_explicit_voice(self):
        params = {
            "video_subject": "한국어 테스트",
            "voice_name": "ko-KR-InJoonNeural-Male",
            "font_name": "",
            "video_language": "ko",
        }
        result = korean_preset.apply_korean_defaults_if_needed(params)
        assert result["voice_name"] == "ko-KR-InJoonNeural-Male"

    def test_replace_chinese_font_for_korean(self):
        params = {
            "video_subject": "한국어 테스트",
            "voice_name": "",
            "font_name": "STHeitiMedium.ttc",
            "video_language": "ko",
        }
        result = korean_preset.apply_korean_defaults_if_needed(params)
        assert result["font_name"] == "NotoSansKR-Bold.ttf"

    def test_explicit_language_override(self):
        params = {
            "video_subject": "This is English but marked as Korean",
            "voice_name": "",
            "font_name": "",
            "video_language": "ko",
        }
        result = korean_preset.apply_korean_defaults_if_needed(params)
        assert "ko-KR" in result["voice_name"]
