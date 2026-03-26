import json
import os
import sys
import tempfile
import time
from unittest.mock import MagicMock, mock_open, patch

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

from app.services import youtube_upload, thumbnail


class TestYouTubeUploadAuth:
    def test_is_authenticated_no_token(self):
        with patch("app.services.youtube_upload._load_token", return_value=None):
            assert youtube_upload.is_authenticated() is False

    def test_is_authenticated_no_refresh_token(self):
        with patch("app.services.youtube_upload._load_token", return_value={"access_token": "abc"}):
            assert youtube_upload.is_authenticated() is False

    def test_is_authenticated_valid(self):
        token = {"access_token": "abc", "refresh_token": "xyz"}
        with patch("app.services.youtube_upload._load_token", return_value=token):
            assert youtube_upload.is_authenticated() is True

    def test_get_auth_url_no_secrets(self):
        with patch("app.services.youtube_upload._load_client_secrets", return_value=None):
            with pytest.raises(ValueError, match="client_secrets.json not found"):
                youtube_upload.get_auth_url()

    def test_get_auth_url_success(self):
        secrets = {"client_id": "test_id", "client_secret": "test_secret"}
        with patch("app.services.youtube_upload._load_client_secrets", return_value=secrets):
            result = youtube_upload.get_auth_url()
            assert "auth_url" in result
            assert "test_id" in result["auth_url"]
            assert "instructions" in result

    @patch("app.services.youtube_upload.requests.post")
    def test_exchange_code_success(self, mock_post):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "access_token": "new_token",
            "refresh_token": "new_refresh",
            "expires_in": 3600,
        }
        mock_resp.raise_for_status = MagicMock()
        mock_post.return_value = mock_resp

        secrets = {"client_id": "id", "client_secret": "secret"}
        with patch("app.services.youtube_upload._load_client_secrets", return_value=secrets):
            with patch("app.services.youtube_upload._save_token"):
                result = youtube_upload.exchange_code("auth_code_123")
                assert result["status"] == "authenticated"


class TestYouTubeUploadVideo:
    def test_upload_video_file_not_found(self):
        with pytest.raises(ValueError, match="Video file not found"):
            youtube_upload.upload_video(
                video_file="/nonexistent/video.mp4",
                title="Test",
            )

    def test_upload_invalid_privacy(self):
        with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as f:
            f.write(b"fake video data")
            temp_path = f.name

        try:
            with patch("app.services.youtube_upload._get_access_token", return_value="token"):
                mock_init_resp = MagicMock()
                mock_init_resp.headers = {"Location": "https://upload.example.com"}
                mock_init_resp.raise_for_status = MagicMock()

                mock_upload_resp = MagicMock()
                mock_upload_resp.json.return_value = {"id": "vid123"}
                mock_upload_resp.raise_for_status = MagicMock()

                with patch("app.services.youtube_upload.requests.post", return_value=mock_init_resp):
                    with patch("app.services.youtube_upload.requests.put", return_value=mock_upload_resp):
                        result = youtube_upload.upload_video(
                            video_file=temp_path,
                            title="Test Video",
                            privacy_status="invalid_status",
                        )
                        assert result["privacy_status"] == "private"
        finally:
            os.unlink(temp_path)


class TestCategoryIDs:
    def test_categories_exist(self):
        assert "entertainment" in youtube_upload.CATEGORY_IDS
        assert "education" in youtube_upload.CATEGORY_IDS
        assert "science" in youtube_upload.CATEGORY_IDS
        assert youtube_upload.CATEGORY_IDS["entertainment"] == "24"


class TestThumbnailPrompt:
    @patch("app.services.thumbnail.llm")
    def test_generate_prompt(self, mock_llm):
        mock_llm._generate_response.return_value = "A vibrant thumbnail showing money and charts"
        result = thumbnail.generate_thumbnail_prompt("돈 아끼는 방법")
        assert "vibrant" in result.lower() or "money" in result.lower()

    @patch("app.services.thumbnail.llm")
    def test_generate_prompt_fallback(self, mock_llm):
        mock_llm._generate_response.return_value = "Error: API failed"
        result = thumbnail.generate_thumbnail_prompt("테스트 주제")
        assert "테스트 주제" in result


class TestThumbnailSimple:
    def test_generate_simple_thumbnail(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = os.path.join(tmpdir, "thumb.png")
            try:
                result = thumbnail.generate_thumbnail_simple(
                    "테스트 썸네일 제목",
                    output_path,
                )
                assert os.path.exists(result)
                assert os.path.getsize(result) > 0
            except ValueError as e:
                if "Pillow" in str(e):
                    pytest.skip("Pillow not installed")
                raise


class TestThumbnailOpenAI:
    @patch("app.services.thumbnail.config")
    def test_no_api_key(self, mock_config):
        mock_config.app = MagicMock()
        mock_config.app.get = MagicMock(return_value="")
        with pytest.raises(ValueError, match="OpenAI API key not configured"):
            thumbnail._generate_with_openai("prompt", "/tmp/out.png")


class TestRefreshToken:
    @patch("app.services.youtube_upload.requests.post")
    @patch("app.services.youtube_upload._load_client_secrets")
    @patch("app.services.youtube_upload._save_token")
    def test_refresh_success(self, mock_save, mock_secrets, mock_post):
        mock_secrets.return_value = {"client_id": "id", "client_secret": "secret"}
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"access_token": "new", "expires_in": 3600}
        mock_resp.raise_for_status = MagicMock()
        mock_post.return_value = mock_resp

        token_data = {"refresh_token": "old_refresh"}
        result = youtube_upload._refresh_token(token_data)
        assert result["access_token"] == "new"
        assert result["refresh_token"] == "old_refresh"

    def test_refresh_no_secrets(self):
        with patch("app.services.youtube_upload._load_client_secrets", return_value=None):
            result = youtube_upload._refresh_token({"refresh_token": "xyz"})
            assert result is None

    def test_refresh_no_refresh_token(self):
        with patch("app.services.youtube_upload._load_client_secrets", return_value={"client_id": "id"}):
            result = youtube_upload._refresh_token({})
            assert result is None
