"""Search and deliver real images without keeping source files on disk."""
from __future__ import annotations

import asyncio
import io
import ipaddress
import re
import secrets
import socket
import time
from dataclasses import dataclass
from urllib.parse import urlsplit

import httpx
from PIL import Image, ImageOps, UnidentifiedImageError

from app.tools.image_search_tool import image_search

MAX_IMAGE_BYTES = 8 * 1024 * 1024
_CACHE: dict[str, tuple[int, float, "FoundImage"]] = {}


@dataclass
class FoundImage:
    data: bytes
    title: str
    source: str


def image_query(text: str) -> str | None:
    text = str(text or "").strip()
    if text.lower().startswith("/image "):
        return text[7:].strip()[:100] or None
    if not re.match(r"^(给我发|发我|发张|来张|找张|找一张|搜一张|给我看张)", text):
        return None
    if not any(word in text for word in ("图", "照片", "壁纸")):
        return None
    query = re.sub(r"^(?:给我发|发我|发张|来张|找张|找一张|搜一张|给我看张)", "", text)
    query = re.sub(r"(?:一张|张|图片|照片|图|壁纸|看看|呗|吧|呀)", "", query).strip(" ：:，,。！？!?")
    if query in ("你", "你的", "萤", "萤的", "你自己", "你自己的"):
        return "萤"
    return query[:100] or None


def _public_https(url: str) -> bool:
    try:
        u = urlsplit(url)
        if u.scheme != "https" or not u.hostname or u.username or u.password or u.port not in (None, 443):
            return False
        answers = socket.getaddrinfo(u.hostname, 443, type=socket.SOCK_STREAM)
        return bool(answers) and all(ipaddress.ip_address(a[4][0]).is_global for a in answers)
    except (ValueError, OSError):
        return False


async def _commons(query: str) -> list[dict]:
    params = {
        "action": "query", "generator": "search", "gsrsearch": query,
        "gsrnamespace": "6", "gsrlimit": "8",
        "prop": "imageinfo", "iiprop": "url|mime", "iiurlwidth": "900", "format": "json",
    }
    async with httpx.AsyncClient(timeout=8) as client:
        r = await client.get("https://commons.wikimedia.org/w/api.php", params=params)
        r.raise_for_status()
        pages = (r.json().get("query") or {}).get("pages") or {}
    return [
        {"title": page.get("title", "").removeprefix("File:"),
         "image_url": info.get("thumburl") or info.get("url"),
         "source_url": info.get("descriptionurl") or ""}
        for page in pages.values()
        for info in (page.get("imageinfo") or [])[:1]
        if info.get("mime") in ("image/jpeg", "image/png", "image/webp")
    ]


def _jpeg(raw: bytes) -> bytes:
    with Image.open(io.BytesIO(raw)) as im:
        im = ImageOps.exif_transpose(im)
        if im.width * im.height > 25_000_000:
            raise ValueError("image dimensions too large")
        im.thumbnail((1500, 1500))
        if im.mode != "RGB":
            background = Image.new("RGB", im.size, "white")
            if "A" in im.getbands():
                background.paste(im, mask=im.getchannel("A"))
            else:
                background.paste(im.convert("RGB"))
            im = background
        buf = io.BytesIO()
        im.save(buf, format="JPEG", quality=85, optimize=True)
        return buf.getvalue()


async def find_image(query: str) -> FoundImage | None:
    query = str(query or "").strip()[:100]
    if not query:
        return None
    # This is a virtual character illustration, never described as a real photograph.
    if query in ("萤", "你", "你自己", "你的样子", "你本人", "萤的照片", "你的照片", "自拍"):
        raw = await asyncio.to_thread(
            lambda: open("/opt/ying/live2d/web/assets/yingbao_model_hd.webp", "rb").read()
        )
        return FoundImage(await asyncio.to_thread(_jpeg, raw), "萤的立绘", "萤的虚拟形象")
    try:
        candidates = await asyncio.wait_for(image_search(query, limit=8), timeout=10)
    except Exception:
        candidates = []
    async with httpx.AsyncClient(timeout=5, follow_redirects=False) as client:
        for item in candidates[:8]:
            url = str(item.get("image_url") or "")
            if not await asyncio.to_thread(_public_https, url):
                continue
            try:
                async with client.stream("GET", url) as r:
                    if r.status_code != 200 or not r.headers.get("content-type", "").lower().startswith("image/"):
                        continue
                    raw = bytearray()
                    async for part in r.aiter_bytes():
                        raw.extend(part)
                        if len(raw) > MAX_IMAGE_BYTES:
                            raise ValueError("image too large")
                jpg = await asyncio.to_thread(_jpeg, bytes(raw))
                return FoundImage(jpg, str(item.get("title") or query)[:80], str(item.get("source_url") or url))
            except (httpx.HTTPError, OSError, ValueError, UnidentifiedImageError):
                continue
        # Commons is an independent fallback. Ask it only when image results
        # could not be downloaded, saving a remote API request on success.
        try:
            commons = await asyncio.wait_for(_commons(query), timeout=8)
        except Exception:
            commons = []
        for item in commons[:6]:
            url = str(item.get("image_url") or "")
            if not await asyncio.to_thread(_public_https, url):
                continue
            try:
                async with client.stream("GET", url) as r:
                    if r.status_code != 200 or not r.headers.get("content-type", "").lower().startswith("image/"):
                        continue
                    raw = bytearray()
                    async for part in r.aiter_bytes():
                        raw.extend(part)
                        if len(raw) > MAX_IMAGE_BYTES:
                            raise ValueError("image too large")
                return FoundImage(await asyncio.to_thread(_jpeg, bytes(raw)), str(item.get("title") or query)[:80], str(item.get("source_url") or url))
            except (httpx.HTTPError, OSError, ValueError, UnidentifiedImageError):
                continue
    return None


def cache_mobile_image(person_id: int, image: FoundImage) -> str:
    now = time.monotonic()
    for token, (_, expiry, _) in list(_CACHE.items()):
        if expiry < now:
            _CACHE.pop(token, None)
    while len(_CACHE) >= 30:
        _CACHE.pop(next(iter(_CACHE)))
    token = secrets.token_urlsafe(24)
    _CACHE[token] = (int(person_id), now + 900, image)
    return token


def get_mobile_image(person_id: int, token: str) -> FoundImage | None:
    entry = _CACHE.get(token)
    if not entry or entry[0] != int(person_id) or entry[1] < time.monotonic():
        return None
    return entry[2]
