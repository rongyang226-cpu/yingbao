import asyncio
import logging

import httpx

log = logging.getLogger(__name__)

from app.config import (
    DEEPSEEK_API_KEY,
    DEEPSEEK_BASE_URL,
    DEEPSEEK_MODEL,
)

# Reuse HTTPS connections across messages. Creating a new client for every
# reply repeatedly pays DNS/TCP/TLS setup cost, which is especially noticeable
# on the Android entry.
_client = None

def _http_client():
    global _client
    if _client is None or _client.is_closed:
        _client = httpx.AsyncClient(
            timeout=httpx.Timeout(45.0, connect=8.0),
            limits=httpx.Limits(max_keepalive_connections=10, max_connections=20),
            http2=False,
        )
    return _client


async def _completion(payload: dict, headers: dict) -> dict:
    # Retry only while connecting: no reply has begun, so the request is safe
    # to send again. Other failures stay visible to the caller.
    for attempt in range(3):
        try:
            response = await _http_client().post(
                f"{DEEPSEEK_BASE_URL}/chat/completions",
                headers=headers,
                json=payload,
            )
            response.raise_for_status()
            data = response.json()
            usage = data.get("usage") or {}
            if "prompt_cache_hit_tokens" in usage:
                log.info(
                    "DeepSeek prompt cache hit=%s miss=%s",
                    usage.get("prompt_cache_hit_tokens", 0),
                    usage.get("prompt_cache_miss_tokens", 0),
                )
            return data
        except (httpx.ConnectTimeout, httpx.ConnectError) as exc:
            if attempt == 2:
                raise
            log.warning(
                "DeepSeek connection failed (%s), retry %s/2",
                type(exc).__name__,
                attempt + 1,
            )
            await asyncio.sleep(0.5 * (2 ** attempt))


async def chat(
    system_prompt: str,
    history: list,
    user_text: str,
    max_tokens: int = 500
) -> str:

    messages = [
        {
            "role": "system",
            "content": system_prompt
        }
    ]

    messages.extend(history)

    messages.append(
        {
            "role": "user",
            "content": user_text
        }
    )

    headers = {
        "Authorization":
            f"Bearer {DEEPSEEK_API_KEY}",
        "Content-Type":
            "application/json",
    }

    payload = {
        "model": DEEPSEEK_MODEL,
        "messages": messages,
        "temperature": 1.1,
        "max_tokens": max_tokens,
    }

    data = await _completion(payload, headers)

    return (
        data["choices"][0]
        ["message"]["content"]
        .strip()
    )


async def extract_json(
    system_prompt: str,
    user_text: str
) -> str:
    headers = {
        "Authorization":
            f"Bearer {DEEPSEEK_API_KEY}",
        "Content-Type":
            "application/json",
    }

    payload = {
        "model": DEEPSEEK_MODEL,
        "messages": [
            {
                "role": "system",
                "content": system_prompt
            },
            {
                "role": "user",
                "content": user_text
            }
        ],
        # 记忆提取需要稳定，不需要创造性
        "temperature": 0.1,
        "max_tokens": 300,
    }

    data = await _completion(payload, headers)

    return (
        data["choices"][0]
        ["message"]["content"]
        .strip()
    )
