import json
import re
from typing import Optional

from loguru import logger

from app.config import config
from app.services import llm

_max_retries = 3


class ScriptLength:
    SHORT = "short"      # Shorts < 60s, ~100-150 words
    MEDIUM = "medium"    # 5-8 min, ~800-1200 words
    LONG = "long"        # 10-15 min, ~1500-2200 words


class SpeechStyle:
    FORMAL = "formal"        # 합니다체
    FRIENDLY = "friendly"    # 해요체
    CASUAL = "casual"        # 해체 (반말)


_LENGTH_CONFIG = {
    ScriptLength.SHORT: {
        "word_count": "100-150 words (Korean: 200-300 characters)",
        "sections": 2,
        "description": "YouTube Shorts format, under 60 seconds",
    },
    ScriptLength.MEDIUM: {
        "word_count": "800-1200 words (Korean: 1600-2400 characters)",
        "sections": 4,
        "description": "Standard YouTube video, 5-8 minutes",
    },
    ScriptLength.LONG: {
        "word_count": "1500-2200 words (Korean: 3000-4400 characters)",
        "sections": 6,
        "description": "In-depth YouTube video, 10-15 minutes",
    },
}

_STYLE_INSTRUCTIONS = {
    SpeechStyle.FORMAL: "Use formal Korean (합니다체). Example endings: ~합니다, ~입니다, ~습니다, ~됩니다",
    SpeechStyle.FRIENDLY: "Use friendly Korean (해요체). Example endings: ~해요, ~이에요, ~예요, ~죠, ~거예요",
    SpeechStyle.CASUAL: "Use casual Korean (해체/반말). Example endings: ~해, ~야, ~지, ~거야, ~인데",
}


def generate_korean_script(
    video_subject: str,
    script_length: str = ScriptLength.MEDIUM,
    speech_style: str = SpeechStyle.FRIENDLY,
    niche: Optional[str] = None,
    target_audience: Optional[str] = None,
    keywords: Optional[list] = None,
    include_visual_cues: bool = True,
) -> dict:
    length_cfg = _LENGTH_CONFIG.get(script_length, _LENGTH_CONFIG[ScriptLength.MEDIUM])
    style_instruction = _STYLE_INSTRUCTIONS.get(speech_style, _STYLE_INSTRUCTIONS[SpeechStyle.FRIENDLY])

    visual_cue_instruction = ""
    if include_visual_cues:
        visual_cue_instruction = """
- Include visual direction cues in the format [B-ROLL: brief description in English]
- Place [B-ROLL] cues between paragraphs or at natural transition points
- Each section should have 1-2 visual cues
- Example: [B-ROLL: aerial city view at sunset]
"""

    niche_context = ""
    if niche:
        niche_context = f"- Content niche/category: {niche}"

    audience_context = ""
    if target_audience:
        audience_context = f"- Target audience: {target_audience}"

    keyword_context = ""
    if keywords:
        keyword_context = f"- Naturally incorporate these keywords: {', '.join(keywords)}"

    prompt = f"""
# Role: Expert Korean YouTube Scriptwriter (한국 유튜브 대본 작가)

You are a professional Korean YouTube scriptwriter who creates engaging,
high-retention scripts optimized for the Korean YouTube market.

## Task
Write a complete YouTube video script in Korean about: {video_subject}

## Script Structure (MUST follow this exact structure)

### HOOK (첫 5초 - 시청자를 잡는 강렬한 오프닝)
- Start with a bold claim, surprising fact, or provocative question
- Create a curiosity gap that makes viewers want to keep watching
- Maximum 2-3 sentences

### CONTEXT (문제 제기 / 배경 설명)
- Explain why this topic matters NOW
- Connect to the viewer's pain point or curiosity
- 2-4 sentences

### MAIN CONTENT (본문 - {length_cfg['sections']} sections)
- Deliver the core value in {length_cfg['sections']} distinct sections
- Each section should have a clear sub-topic
- End each section with a mini-cliffhanger or transition to maintain retention
- Use specific examples, data, or stories - avoid vague generalizations

### ENGAGEMENT (참여 유도 - 중간 삽입)
- Place naturally between main content sections
- Ask viewers to like, comment with their opinion, or share
- Make it conversational, not forced
- Example: "여러분은 어떻게 생각하세요? 댓글로 알려주세요"

### CONCLUSION (마무리 + CTA)
- Summarize the key takeaway in 1-2 sentences
- End with a clear call-to-action (subscribe, next video tease)
- Leave the viewer with something to think about

## Writing Rules
1. {style_instruction}
2. Write for SPOKEN delivery, not reading - use short sentences (8-15 words average)
3. Include natural pauses with [PAUSE] markers for dramatic effect
4. Total length: {length_cfg['word_count']}
5. Format: {length_cfg['description']}
6. Do NOT use markdown formatting (no #, *, etc.)
7. Do NOT include section labels in the output - just write the script naturally
8. Each paragraph should flow into the next
9. Use Konglish/English loan words naturally where appropriate
10. Avoid overly formal or written-style Korean expressions
{visual_cue_instruction}
{niche_context}
{audience_context}
{keyword_context}

## Output Format
Return the script as a JSON object with this structure:
{{
  "hook": "The hook text (first 5 seconds)",
  "context": "The context/problem setup",
  "sections": [
    {{
      "content": "Section 1 content",
      "visual_cue": "B-roll description for this section"
    }},
    {{
      "content": "Section 2 content",
      "visual_cue": "B-roll description for this section"
    }}
  ],
  "engagement": "Mid-video engagement prompt",
  "conclusion": "Conclusion with CTA",
  "full_script": "The complete script as a single string for TTS (no visual cues, no section markers)",
  "estimated_duration_seconds": 300,
  "search_terms": ["english search term 1", "english search term 2", "english search term 3"]
}}

Return ONLY the JSON object. No other text.
""".strip()

    logger.info(f"generating Korean script: subject={video_subject}, length={script_length}, style={speech_style}")

    result = None
    response = ""
    for i in range(_max_retries):
        try:
            response = llm._generate_response(prompt)
            if "Error: " in response:
                logger.error(f"LLM error: {response}")
                continue

            result = json.loads(response)
            if isinstance(result, dict) and "full_script" in result:
                break
        except json.JSONDecodeError:
            if response:
                match = re.search(r"\{.*\}", response, re.DOTALL)
                if match:
                    try:
                        result = json.loads(match.group())
                        if isinstance(result, dict) and "full_script" in result:
                            break
                    except json.JSONDecodeError:
                        pass
            logger.warning(f"failed to parse script JSON, attempt {i + 1}/{_max_retries}")

    if not result or "full_script" not in result:
        logger.warning("structured script generation failed, falling back to plain text")
        return _fallback_plain_script(video_subject, speech_style, length_cfg)

    validated = {
        "hook": result.get("hook", ""),
        "context": result.get("context", ""),
        "sections": result.get("sections", []),
        "engagement": result.get("engagement", ""),
        "conclusion": result.get("conclusion", ""),
        "full_script": result.get("full_script", ""),
        "estimated_duration_seconds": int(result.get("estimated_duration_seconds", 0)),
        "search_terms": result.get("search_terms", []),
        "script_length": script_length,
        "speech_style": speech_style,
        "video_subject": video_subject,
    }

    logger.success(
        f"generated Korean script: {len(validated['full_script'])} chars, "
        f"~{validated['estimated_duration_seconds']}s, "
        f"{len(validated['sections'])} sections"
    )
    return validated


def _fallback_plain_script(
    video_subject: str,
    speech_style: str,
    length_cfg: dict,
) -> dict:
    style_instruction = _STYLE_INSTRUCTIONS.get(speech_style, _STYLE_INSTRUCTIONS[SpeechStyle.FRIENDLY])

    prompt = f"""
한국어 유튜브 영상 대본을 작성해주세요.

주제: {video_subject}
문체: {style_instruction}
길이: {length_cfg['word_count']}

규칙:
- 마크다운 사용 금지
- 말하는 듯한 자연스러운 문체로 작성
- 짧은 문장 사용 (8-15 단어)
- 대본 내용만 반환 (다른 설명 없이)
""".strip()

    response = ""
    for i in range(_max_retries):
        try:
            response = llm._generate_response(prompt)
            if response and "Error: " not in response:
                break
        except Exception as e:
            logger.error(f"fallback script generation failed: {e}")

    clean = response.replace("*", "").replace("#", "")
    clean = re.sub(r"\[.*?\]", "", clean)
    clean = re.sub(r"\(.*?\)", "", clean)

    return {
        "hook": "",
        "context": "",
        "sections": [],
        "engagement": "",
        "conclusion": "",
        "full_script": clean.strip(),
        "estimated_duration_seconds": 0,
        "search_terms": [],
        "script_length": "medium",
        "speech_style": speech_style,
        "video_subject": video_subject,
    }


def review_script(script_text: str) -> dict:
    prompt = f"""
# Role: YouTube Script Quality Reviewer

Review the following Korean YouTube script and rate it.

## Script
{script_text}

## Evaluation Criteria
Rate each criterion from 1-10:
1. hook_strength: How compelling is the opening? Will it stop the scroll?
2. information_density: Is the content valuable and specific (not vague)?
3. engagement: Are there natural engagement prompts? Will viewers comment?
4. pacing: Does the script flow well? Are sentences the right length for speaking?
5. retention: Will viewers watch to the end? Are there mini-cliffhangers?

## Output Format
Return ONLY a JSON object:
{{
  "hook_strength": 8,
  "information_density": 7,
  "engagement": 6,
  "pacing": 8,
  "retention": 7,
  "overall_score": 7.2,
  "improvements": ["specific improvement suggestion 1", "specific improvement suggestion 2"],
  "improvements_ko": ["구체적 개선 제안 1", "구체적 개선 제안 2"]
}}
""".strip()

    logger.info("reviewing script quality")

    for i in range(_max_retries):
        try:
            response = llm._generate_response(prompt)
            if "Error: " in response:
                continue

            result = json.loads(response)
            if isinstance(result, dict) and "overall_score" in result:
                logger.success(f"script review: overall_score={result['overall_score']}")
                return result
        except json.JSONDecodeError:
            if response:
                match = re.search(r"\{.*\}", response, re.DOTALL)
                if match:
                    try:
                        result = json.loads(match.group())
                        if isinstance(result, dict) and "overall_score" in result:
                            return result
                    except json.JSONDecodeError:
                        pass
            logger.warning(f"failed to parse review JSON, attempt {i + 1}/{_max_retries}")

    return {
        "hook_strength": 0,
        "information_density": 0,
        "engagement": 0,
        "pacing": 0,
        "retention": 0,
        "overall_score": 0,
        "improvements": ["Review failed - could not parse LLM response"],
        "improvements_ko": ["리뷰 실패 - LLM 응답 파싱 불가"],
    }


def generate_from_topic(topic: dict, script_length: str = ScriptLength.MEDIUM, speech_style: str = SpeechStyle.FRIENDLY) -> dict:
    video_subject = topic.get("title_ko") or topic.get("title", "")
    keywords = topic.get("keywords", [])
    description = topic.get("description_ko") or topic.get("description", "")

    if description:
        video_subject = f"{video_subject} - {description}"

    return generate_korean_script(
        video_subject=video_subject,
        script_length=script_length,
        speech_style=speech_style,
        keywords=keywords,
        include_visual_cues=True,
    )
