from fastapi import Request

from app.controllers.v1.base import new_router
from app.services import thumbnail, youtube_upload
from app.utils import utils

router = new_router()


@router.get(
    "/youtube/auth/status",
    summary="Check YouTube OAuth authentication status",
)
def auth_status():
    authenticated = youtube_upload.is_authenticated()
    return utils.get_response(200, {"authenticated": authenticated})


@router.get(
    "/youtube/auth/url",
    summary="Get YouTube OAuth authorization URL",
)
def auth_url():
    result = youtube_upload.get_auth_url()
    return utils.get_response(200, result)


@router.post(
    "/youtube/auth/callback",
    summary="Exchange OAuth authorization code for access token",
)
def auth_callback(request: Request, body: dict):
    code = body.get("code", "")
    if not code:
        return utils.get_response(400, message="Authorization code is required")
    result = youtube_upload.exchange_code(code)
    return utils.get_response(200, result)


@router.post(
    "/youtube/upload",
    summary="Upload a video to YouTube",
)
def upload_video(request: Request, body: dict):
    video_file = body.get("video_file", "")
    title = body.get("title", "")
    description = body.get("description", "")
    tags = body.get("tags", [])
    category_id = body.get("category_id", "22")
    privacy_status = body.get("privacy_status", "private")
    thumbnail_file = body.get("thumbnail_file")
    default_language = body.get("default_language", "ko")

    if not video_file:
        return utils.get_response(400, message="video_file is required")
    if not title:
        return utils.get_response(400, message="title is required")

    result = youtube_upload.upload_video(
        video_file=video_file,
        title=title,
        description=description,
        tags=tags,
        category_id=category_id,
        privacy_status=privacy_status,
        thumbnail_file=thumbnail_file,
        default_language=default_language,
    )
    return utils.get_response(200, result)


@router.post(
    "/youtube/upload-task",
    summary="Upload a completed task's video to YouTube",
)
def upload_task_video(request: Request, body: dict):
    from app.services import state as sm

    task_id = body.get("task_id", "")
    title = body.get("title", "")
    description = body.get("description", "")
    tags = body.get("tags", [])
    category_id = body.get("category_id", "22")
    privacy_status = body.get("privacy_status", "private")
    generate_thumbnail = body.get("generate_thumbnail", True)
    use_ai_thumbnail = body.get("use_ai_thumbnail", False)
    default_language = body.get("default_language", "ko")

    if not task_id:
        return utils.get_response(400, message="task_id is required")

    task = sm.state.get_task(task_id)
    if not task:
        return utils.get_response(404, message="Task not found")

    videos = task.get("videos", [])
    if not videos:
        return utils.get_response(400, message="Task has no completed videos")

    video_file = videos[0]
    if not title:
        title = task.get("video_subject", "Untitled Video")

    thumbnail_file = None
    if generate_thumbnail:
        try:
            video_subject = task.get("video_subject", title)
            thumbnail_file = thumbnail.generate_for_task(
                task_id=task_id,
                video_subject=video_subject,
                title_text=title,
                use_ai=use_ai_thumbnail,
            )
        except Exception as e:
            from loguru import logger
            logger.warning(f"thumbnail generation failed: {e}")

    result = youtube_upload.upload_video(
        video_file=video_file,
        title=title,
        description=description,
        tags=tags,
        category_id=category_id,
        privacy_status=privacy_status,
        thumbnail_file=thumbnail_file,
        default_language=default_language,
    )
    result["task_id"] = task_id
    return utils.get_response(200, result)


@router.post(
    "/thumbnails/generate",
    summary="Generate a thumbnail image",
)
def generate_thumbnail(request: Request, body: dict):
    video_subject = body.get("video_subject", "")
    title_text = body.get("title_text", "")
    use_ai = body.get("use_ai", False)
    task_id = body.get("task_id", "")

    if not video_subject and not title_text:
        return utils.get_response(400, message="video_subject or title_text is required")

    if task_id:
        output_path = thumbnail.generate_for_task(
            task_id=task_id,
            video_subject=video_subject or title_text,
            title_text=title_text,
            use_ai=use_ai,
        )
    else:
        import uuid
        temp_id = str(uuid.uuid4())
        output_path = thumbnail.generate_for_task(
            task_id=temp_id,
            video_subject=video_subject or title_text,
            title_text=title_text,
            use_ai=use_ai,
        )

    return utils.get_response(200, {"thumbnail_path": output_path})


@router.get(
    "/youtube/categories",
    summary="List available YouTube video categories",
)
def get_categories():
    return utils.get_response(200, {"categories": youtube_upload.CATEGORY_IDS})
