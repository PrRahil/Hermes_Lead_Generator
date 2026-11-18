from __future__ import annotations

import json
import logging
from typing import Any, Optional

from hermes.config import Settings, get_settings

logger = logging.getLogger(__name__)


def _client(settings: Settings):
    from openai import OpenAI

    headers = {}
    if settings.uses_openrouter:
        headers = {
            "HTTP-Referer": settings.openrouter_http_referer,
            "X-Title": settings.openrouter_app_title,
        }
    return OpenAI(
        api_key=settings.llm_api_key,
        base_url=settings.openai_base_url,
        default_headers=headers or None,
    )


def chat_json(system: str, user: str, *, fallback: Optional[dict] = None) -> dict:
    settings = get_settings()
    if not settings.llm_enabled:
        return fallback or {}

    try:
        client = _client(settings)
        resp = client.chat.completions.create(
            model=settings.openai_model,
            temperature=0.3,
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        )
        content = resp.choices[0].message.content or "{}"
        return json.loads(content)
    except Exception as exc:
        logger.warning("LLM JSON call failed (%s): %s", settings.openai_model, exc)
        return fallback or {}


def chat_text(system: str, user: str, *, fallback: str = "") -> str:
    settings = get_settings()
    if not settings.llm_enabled:
        return fallback
    try:
        client = _client(settings)
        resp = client.chat.completions.create(
            model=settings.openai_model,
            temperature=0.5,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        )
        return (resp.choices[0].message.content or fallback).strip()
    except Exception as exc:
        logger.warning("LLM text call failed (%s): %s", settings.openai_model, exc)
        return fallback


def serper_search(query: str, num: int = 5) -> list[dict[str, Any]]:
    settings = get_settings()
    if not settings.serper_api_key:
        return []
    try:
        import httpx

        resp = httpx.post(
            "https://google.serper.dev/search",
            headers={"X-API-KEY": settings.serper_api_key, "Content-Type": "application/json"},
            json={"q": query, "num": num},
            timeout=20.0,
        )
        resp.raise_for_status()
        data = resp.json()
        return data.get("organic", [])
    except Exception:
        return []
