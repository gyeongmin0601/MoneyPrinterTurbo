"""
YouTube video upload service using YouTube Data API v3.

Requires OAuth 2.0 credentials (not just an API key).
Setup:
1. Create OAuth 2.0 credentials at https://console.cloud.google.com/apis/credentials
2. Download client_secrets.json and place in project root
3. Run the auth flow once to generate youtube_oauth_token.json

Upload quota cost: 1,600 units per upload.
"""

import json
import os
import time
from typing import Optional

import requests
from loguru import logger

from app.config import config
from app.utils import utils

_TOKEN_FILE = os.path.join(utils.root_dir(), "youtube_oauth_token.json")
_CLIENT_SECRETS_FILE = os.path.join(utils.root_dir(), "client_secrets.json")

YOUTUBE_UPLOAD_URL = "https://www.googleapis.com/upload/youtube/v3/videos"
YOUTUBE_VIDEOS_URL = "https://www.googleapis.com/youtube/v3/videos"
YOUTUBE_THUMBNAILS_URL = "https://www.googleapis.com/youtube/v3/thumbnails/set"

VALID_PRIVACY_STATUSES = ["public", "private", "unlisted"]

CATEGORY_IDS = {
    "film": "1",
    "autos": "2",
    "music": "10",
    "pets": "15",
    "sports": "17",
    "gaming": "20",
    "people": "22",
    "comedy": "23",
    "entertainment": "24",
    "news": "25",
    "howto": "26",
    "education": "27",
    "science": "28",
    "nonprofits": "29",
}


def _load_token() -> Optional[dict]:
    if not os.path.exists(_TOKEN_FILE):
        return None
    try:
        with open(_TOKEN_FILE, "r") as f:
            return json.load(f)
    except Exception as e:
        logger.error(f"failed to load OAuth token: {e}")
        return None


def _save_token(token_data: dict):
    with open(_TOKEN_FILE, "w") as f:
        json.dump(token_data, f, indent=2)
    logger.info("OAuth token saved")


def _load_client_secrets() -> Optional[dict]:
    if not os.path.exists(_CLIENT_SECRETS_FILE):
        return None
    try:
        with open(_CLIENT_SECRETS_FILE, "r") as f:
            data = json.load(f)
            installed = data.get("installed") or data.get("web")
            return installed
    except Exception as e:
        logger.error(f"failed to load client secrets: {e}")
        return None


def _refresh_token(token_data: dict) -> Optional[dict]:
    secrets = _load_client_secrets()
    if not secrets:
        logger.error("client_secrets.json not found, cannot refresh token")
        return None

    refresh_token = token_data.get("refresh_token")
    if not refresh_token:
        logger.error("no refresh_token in token data")
        return None

    try:
        resp = requests.post(
            "https://oauth2.googleapis.com/token",
            data={
                "client_id": secrets["client_id"],
                "client_secret": secrets["client_secret"],
                "refresh_token": refresh_token,
                "grant_type": "refresh_token",
            },
            timeout=30,
        )
        resp.raise_for_status()
        new_token = resp.json()
        new_token["refresh_token"] = refresh_token
        _save_token(new_token)
        logger.info("OAuth token refreshed")
        return new_token
    except Exception as e:
        logger.error(f"failed to refresh token: {e}")
        return None


def _get_access_token() -> str:
    token_data = _load_token()
    if not token_data:
        raise ValueError(
            "YouTube OAuth token not found. "
            "Run 'python scripts/youtube_auth.py' to authenticate first."
        )

    expires_at = token_data.get("expires_at", 0)
    if time.time() >= expires_at - 60:
        token_data = _refresh_token(token_data)
        if not token_data:
            raise ValueError("Failed to refresh OAuth token. Re-authenticate.")

    return token_data["access_token"]


def get_auth_url() -> dict:
    secrets = _load_client_secrets()
    if not secrets:
        raise ValueError(
            "client_secrets.json not found. "
            "Download it from Google Cloud Console."
        )

    auth_url = (
        f"https://accounts.google.com/o/oauth2/v2/auth?"
        f"client_id={secrets['client_id']}"
        f"&redirect_uri=urn:ietf:wg:oauth:2.0:oob"
        f"&response_type=code"
        f"&scope=https://www.googleapis.com/auth/youtube.upload"
        f"%20https://www.googleapis.com/auth/youtube"
        f"&access_type=offline"
        f"&prompt=consent"
    )

    return {
        "auth_url": auth_url,
        "instructions": "Visit the URL, authorize, and paste the code to /api/v1/youtube/callback",
    }


def exchange_code(auth_code: str) -> dict:
    secrets = _load_client_secrets()
    if not secrets:
        raise ValueError("client_secrets.json not found")

    try:
        resp = requests.post(
            "https://oauth2.googleapis.com/token",
            data={
                "client_id": secrets["client_id"],
                "client_secret": secrets["client_secret"],
                "code": auth_code,
                "grant_type": "authorization_code",
                "redirect_uri": "urn:ietf:wg:oauth:2.0:oob",
            },
            timeout=30,
        )
        resp.raise_for_status()
        token_data = resp.json()
        token_data["expires_at"] = time.time() + token_data.get("expires_in", 3600)
        _save_token(token_data)
        logger.success("YouTube OAuth authentication complete")
        return {"status": "authenticated", "expires_in": token_data.get("expires_in")}
    except Exception as e:
        raise ValueError(f"Failed to exchange auth code: {e}")


def is_authenticated() -> bool:
    token_data = _load_token()
    if not token_data:
        return False
    if not token_data.get("refresh_token"):
        return False
    return True


def upload_video(
    video_file: str,
    title: str,
    description: str = "",
    tags: Optional[list] = None,
    category_id: str = "22",
    privacy_status: str = "private",
    thumbnail_file: Optional[str] = None,
    default_language: str = "ko",
) -> dict:
    if not os.path.exists(video_file):
        raise ValueError(f"Video file not found: {video_file}")

    if privacy_status not in VALID_PRIVACY_STATUSES:
        privacy_status = "private"

    access_token = _get_access_token()
    headers = {"Authorization": f"Bearer {access_token}"}

    metadata = {
        "snippet": {
            "title": title[:100],
            "description": description[:5000],
            "tags": (tags or [])[:500],
            "categoryId": category_id,
            "defaultLanguage": default_language,
        },
        "status": {
            "privacyStatus": privacy_status,
            "selfDeclaredMadeForKids": False,
        },
    }

    logger.info(f"uploading video: {title} ({privacy_status})")

    try:
        file_size = os.path.getsize(video_file)

        resp = requests.post(
            f"{YOUTUBE_UPLOAD_URL}?uploadType=resumable&part=snippet,status",
            headers={
                **headers,
                "Content-Type": "application/json; charset=UTF-8",
                "X-Upload-Content-Length": str(file_size),
                "X-Upload-Content-Type": "video/mp4",
            },
            json=metadata,
            timeout=30,
        )
        resp.raise_for_status()

        upload_url = resp.headers.get("Location")
        if not upload_url:
            raise ValueError("No upload URL returned from YouTube API")

        with open(video_file, "rb") as f:
            upload_resp = requests.put(
                upload_url,
                headers={
                    "Content-Type": "video/mp4",
                    "Content-Length": str(file_size),
                },
                data=f,
                timeout=600,
            )
            upload_resp.raise_for_status()

        video_data = upload_resp.json()
        video_id = video_data.get("id", "")
        logger.success(f"video uploaded: https://youtu.be/{video_id}")

        result = {
            "video_id": video_id,
            "url": f"https://youtu.be/{video_id}",
            "title": title,
            "privacy_status": privacy_status,
        }

        if thumbnail_file and os.path.exists(thumbnail_file):
            try:
                thumb_result = set_thumbnail(video_id, thumbnail_file)
                result["thumbnail_set"] = True
                result["thumbnail_url"] = thumb_result.get("url", "")
            except Exception as e:
                logger.warning(f"failed to set thumbnail: {e}")
                result["thumbnail_set"] = False

        return result

    except requests.exceptions.HTTPError as e:
        error_body = ""
        try:
            error_body = e.response.json()
        except Exception:
            error_body = e.response.text
        raise ValueError(f"YouTube upload failed: {error_body}")
    except Exception as e:
        raise ValueError(f"YouTube upload failed: {e}")


def set_thumbnail(video_id: str, thumbnail_file: str) -> dict:
    if not os.path.exists(thumbnail_file):
        raise ValueError(f"Thumbnail file not found: {thumbnail_file}")

    access_token = _get_access_token()

    with open(thumbnail_file, "rb") as f:
        content_type = "image/png"
        if thumbnail_file.lower().endswith(".jpg") or thumbnail_file.lower().endswith(".jpeg"):
            content_type = "image/jpeg"

        resp = requests.post(
            f"{YOUTUBE_THUMBNAILS_URL}?videoId={video_id}",
            headers={
                "Authorization": f"Bearer {access_token}",
                "Content-Type": content_type,
            },
            data=f,
            timeout=60,
        )
        resp.raise_for_status()

    data = resp.json()
    thumbnail_url = (
        data.get("items", [{}])[0]
        .get("high", {})
        .get("url", "")
    )
    logger.success(f"thumbnail set for {video_id}")
    return {"video_id": video_id, "url": thumbnail_url}
