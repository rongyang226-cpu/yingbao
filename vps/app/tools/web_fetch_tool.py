from __future__ import annotations

import asyncio
import gzip
import zlib
import ipaddress
import re
import socket
import urllib.parse
import urllib.request
from html import unescape
from html.parser import HTMLParser


MAX_BYTES = 900_000


class _TextExtractor(HTMLParser):
    def __init__(self):
        super().__init__()
        self.skip = 0
        self.parts = []

    def handle_starttag(self, tag, attrs):
        if tag in {"script", "style", "noscript", "svg"}:
            self.skip += 1

    def handle_endtag(self, tag):
        if tag in {"script", "style", "noscript", "svg"} and self.skip:
            self.skip -= 1

    def handle_data(self, data):
        if self.skip:
            return
        text = re.sub(r"\s+", " ", data).strip()
        if len(text) >= 20:
            self.parts.append(text)


def _public_host(hostname: str) -> bool:
    try:
        infos = socket.getaddrinfo(hostname, None)
    except Exception:
        return False

    for info in infos:
        ip = info[4][0]
        try:
            addr = ipaddress.ip_address(ip)
        except ValueError:
            return False

        if (
            addr.is_private
            or addr.is_loopback
            or addr.is_link_local
            or addr.is_reserved
            or addr.is_multicast
        ):
            return False

    return True


def _fetch_sync(url: str, max_chars: int):
    parsed = urllib.parse.urlparse(url)

    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise ValueError("unsupported url")

    if not _public_host(parsed.hostname):
        raise ValueError("non-public host blocked")

    class _SafeRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, request, fp, code, msg, headers, newurl):
            target = urllib.parse.urlparse(newurl)
            if target.scheme not in {"http", "https"} or not target.hostname or not _public_host(target.hostname):
                raise ValueError("redirect to non-public host blocked")
            return super().redirect_request(request, fp, code, msg, headers, newurl)

    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0 (Ying Research/1.0)",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.7",
            "Accept-Encoding": "identity",
        },
    )

    with urllib.request.build_opener(_SafeRedirect).open(req, timeout=12) as resp:
        content_type = (resp.headers.get("Content-Type") or "").lower()
        if "text/html" not in content_type and "text/plain" not in content_type:
            return {
                "url": resp.geturl(),
                "text": "",
                "content_type": content_type,
            }

        raw = resp.read(MAX_BYTES + 1)
        encoding = (resp.headers.get("Content-Encoding") or "").lower().strip()
        charset = resp.headers.get_content_charset() or "utf-8"

    if len(raw) > MAX_BYTES:
        return {"url": resp.geturl(), "text": "", "content_type": content_type}
    if encoding == "gzip" or raw.startswith(b"\x1f\x8b"):
        dec = zlib.decompressobj(16 + zlib.MAX_WBITS)
        raw = dec.decompress(raw, MAX_BYTES + 1)
    elif encoding == "deflate":
        dec = zlib.decompressobj()
        raw = dec.decompress(raw, MAX_BYTES + 1)
    if len(raw) > MAX_BYTES or b"\x00" in raw[:4096]:
        return {"url": resp.geturl(), "text": "", "content_type": content_type}
    try:
        text = raw.decode(charset, errors="replace")
    except LookupError:
        text = raw.decode("utf-8", errors="replace")

    if "text/html" in content_type:
        parser = _TextExtractor()
        parser.feed(text)
        text = "\n".join(parser.parts)

    text = unescape(text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = text.strip()

    return {
        "url": resp.geturl(),
        "text": text[:max_chars],
        "content_type": content_type,
    }


async def fetch_page_text(url: str, max_chars: int = 4500):
    return await asyncio.to_thread(
        _fetch_sync,
        str(url),
        int(max_chars),
    )
