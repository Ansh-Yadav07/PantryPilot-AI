"""
Minimal Gemini REST client (generativelanguage.googleapis.com v1beta).

Replaces the deprecated `google-generativeai` SDK. Tries each configured model
in order and falls through on overload (503), rate limiting (429) or model
errors, so a single busy model does not break the feature.

The API key never leaves the backend.
"""

import base64
import json
import logging
import re
from typing import Any, List, Optional, Union

import httpx

from ..config.settings import settings

logger = logging.getLogger("pantrypilot.gemini")

API_BASE = "https://generativelanguage.googleapis.com/v1beta/models"


class GeminiNotConfigured(RuntimeError):
    """GEMINI_API_KEY is missing."""


class GeminiError(RuntimeError):
    """Every configured model failed, or returned unusable output."""


Part = Union[str, dict]


def image_part(data: bytes, mime_type: str) -> dict:
    return {"inline_data": {"mime_type": mime_type, "data": base64.b64encode(data).decode("ascii")}}


def is_configured() -> bool:
    return bool(settings.gemini_api_key)


def _to_parts(parts: List[Part]) -> List[dict]:
    return [{"text": p} if isinstance(p, str) else p for p in parts]


def _extract_text(body: dict) -> str:
    candidates = body.get("candidates") or []
    if not candidates:
        reason = (body.get("promptFeedback") or {}).get("blockReason")
        raise GeminiError(f"Request was blocked ({reason})" if reason else "Empty response")
    cand = candidates[0]
    finish = cand.get("finishReason")
    if finish in ("SAFETY", "RECITATION", "PROHIBITED_CONTENT", "BLOCKLIST", "SPII"):
        raise GeminiError(f"Response blocked ({finish})")
    texts = [p.get("text", "") for p in (cand.get("content") or {}).get("parts", [])
             if "text" in p and not p.get("thought")]
    text = "".join(texts).strip()
    if not text:
        raise GeminiError(f"No text in response (finishReason={finish})")
    return text


def _strip_fences(text: str) -> str:
    text = text.strip()
    m = re.match(r"^```(?:json)?\s*(.*?)\s*```$", text, re.DOTALL)
    return m.group(1) if m else text


def generate_text(parts: List[Part], *, timeout: float = 30.0, json_output: bool = False,
                  temperature: Optional[float] = None) -> str:
    if not settings.gemini_api_key:
        raise GeminiNotConfigured("GEMINI_API_KEY is not configured")

    gen_config: dict = {}
    if json_output:
        gen_config["responseMimeType"] = "application/json"
    if temperature is not None:
        gen_config["temperature"] = temperature
    payload = {"contents": [{"role": "user", "parts": _to_parts(parts)}]}
    if gen_config:
        payload["generationConfig"] = gen_config

    headers = {"x-goog-api-key": settings.gemini_api_key, "Content-Type": "application/json"}
    errors: List[str] = []
    with httpx.Client(timeout=httpx.Timeout(timeout, connect=10.0)) as client:
        for model in settings.gemini_model_list:
            try:
                resp = client.post(f"{API_BASE}/{model}:generateContent", headers=headers, json=payload)
            except httpx.HTTPError as e:
                errors.append(f"{model}: {type(e).__name__}")
                continue
            if resp.status_code == 200:
                try:
                    return _extract_text(resp.json())
                except GeminiError as e:
                    errors.append(f"{model}: {e}")
                    continue
            # 400 with an invalid key affects every model: stop early.
            if resp.status_code in (401, 403) or (resp.status_code == 400 and "API key" in resp.text):
                logger.error("Gemini rejected the API key (HTTP %s)", resp.status_code)
                raise GeminiError("The AI service rejected the server's API key.")
            errors.append(f"{model}: HTTP {resp.status_code}")
    logger.warning("All Gemini models failed: %s", "; ".join(errors))
    raise GeminiError("The AI service is temporarily unavailable. Please try again shortly.")


def generate_json(parts: List[Part], *, timeout: float = 30.0, temperature: Optional[float] = None) -> Any:
    text = generate_text(parts, timeout=timeout, json_output=True, temperature=temperature)
    try:
        return json.loads(_strip_fences(text), strict=False)
    except json.JSONDecodeError:
        logger.warning("Gemini returned invalid JSON (%d chars)", len(text))
        raise GeminiError("The AI service returned an unreadable response. Please try again.")
