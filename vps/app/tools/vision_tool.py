from __future__ import annotations

import asyncio
import base64
import mimetypes
import os
from pathlib import Path

from openai import OpenAI
from dotenv import load_dotenv

load_dotenv("/opt/ying/.env")


def _guess_mime(path: str) -> str:
    mime, _ = mimetypes.guess_type(path)

    if mime in {
        "image/jpeg",
        "image/png",
        "image/gif",
        "image/webp",
    }:
        return mime

    return "image/jpeg"


def _analyze_image_sync(
    image_path: str,
    prompt: str,
) -> str:
    path = Path(image_path)

    if not path.exists():
        raise FileNotFoundError(image_path)

    api_key = os.getenv("DEEPSEEK_API_KEY")

    if not api_key:
        raise RuntimeError("DEEPSEEK_API_KEY missing")

    raw = path.read_bytes()

    b64 = base64.b64encode(raw).decode("ascii")
    mime = _guess_mime(str(path))

    data_url = f"data:{mime};base64,{b64}"

    client = OpenAI(
        api_key=api_key,
        base_url="https://api.deepseek.com",
    )

    safe_prompt = (
        "你负责视觉理解。只描述画面中可以确认的内容。"
        "不要根据脸部识别或猜测现实人物身份；"
        "不要从外表猜测敏感属性、健康状况、政治立场等。"
        "看不清、不确定或被遮挡的内容就明确说不确定。\n\n"
        + prompt
    )

    response = client.chat.completions.create(
        model="deepseek-flash",
        messages=[
            {
                "role": "user",
                "content": [
                    {
                        "type": "text",
                        "text": safe_prompt,
                    },
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": data_url,
                        },
                    },
                ],
            }
        ],
        max_tokens=500,
    )

    return (
        response.choices[0].message.content
        or ""
    ).strip()


async def analyze_image(
    image_path: str,
    prompt: str = (
        "请用中文描述这张图片中的主要内容。"
        "如果包含文字，请同时概括重要文字。"
        "不要猜测看不清的细节。"
    ),
) -> str:
    return await asyncio.to_thread(
        _analyze_image_sync,
        image_path,
        prompt,
    )
