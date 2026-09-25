from __future__ import annotations

import asyncio
import json
import urllib.parse
import urllib.request


SEARXNG_URL = "http://127.0.0.1:8888/search"


def _search_images_sync(
    query: str,
    *,
    limit: int = 5,
):
    params = {
        "q": query,
        "format": "json",
        "categories": "images",
        "engines": "wikicommons.images,bing images",
        "language": "auto",
    }

    url = (
        SEARXNG_URL
        + "?"
        + urllib.parse.urlencode(params)
    )

    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": "Ying-AI-Companion/1.0",
        },
    )

    with urllib.request.urlopen(
        req,
        timeout=8,
    ) as resp:
        data = json.loads(
            resp.read().decode("utf-8")
        )

    output = []

    for item in (data.get("results") or [])[:limit]:
        image_url = (
            item.get("img_src")
            or item.get("thumbnail_src")
        )

        if not image_url:
            continue

        output.append({
            "title": item.get("title"),
            "image_url": image_url,
            "source_url": item.get("url"),
            "engine": item.get("engine"),
        })

    return output


async def image_search(
    query: str,
    limit: int = 5,
):
    query = str(query or "").strip()

    if not query:
        return []

    return await asyncio.to_thread(
        _search_images_sync,
        query,
        limit=limit,
    )
