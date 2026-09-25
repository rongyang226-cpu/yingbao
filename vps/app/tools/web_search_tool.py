from __future__ import annotations

import asyncio
import json
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
import time
import re

from app.tools.web_fetch_tool import fetch_page_text


SEARXNG_URL = "http://127.0.0.1:8888/search"
BING_RSS_URL = "https://www.bing.com/search"
BING_NEWS_RSS_URL = "https://www.bing.com/news/search"


def _request_json(url, *, timeout=15):
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0 (Ying Search/1.0)",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.7",
        },
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8", errors="replace"))


def _query_terms(query: str):
    q = str(query or "").lower()
    latin = [
        x for x in re.findall(r"[a-z0-9]{3,}", q)
        if x not in {"the", "and", "for", "with", "latest", "news"}
    ]
    for word in ("今天", "今日", "最新", "新闻", "刚刚", "一下", "帮我"):
        q = q.replace(word, "")
    han = re.findall(r"[\u4e00-\u9fff]{2,}", q)
    return latin + han


def _looks_relevant(query: str, item: dict) -> bool:
    terms = _query_terms(query)
    if not terms:
        return True

    hay = " ".join([
        str(item.get("title") or ""),
        str(item.get("content") or ""),
        str(item.get("url") or ""),
    ]).lower()

    return any(term.lower() in hay for term in terms)


def _normalize_searx(data, limit, query=""):
    output = []
    seen = set()

    for item in data.get("results") or []:
        url = str(item.get("url") or "").strip()
        title = str(item.get("title") or "").strip()
        if not url or not title or url in seen:
            continue

        normalized = {
            "title": title,
            "url": url,
            "content": str(item.get("content") or "").strip(),
            "engine": item.get("engine") or "searxng",
            "source": "searxng",
        }

        if query and not _looks_relevant(query, normalized):
            continue

        seen.add(url)
        output.append(normalized)
        if len(output) >= limit:
            break

    return output


def _searx_search_sync(query: str, limit: int):
    search_query = re.sub(r"^(今天|今日|最新|刚刚)", "", query).strip() or query
    params = {
        "q": search_query,
        "format": "json",
        "categories": "general",
        "engines": "bing",
        "language": "zh-CN" if re.search(r"[\u4e00-\u9fff]", query) else "en",
    }
    url = SEARXNG_URL + "?" + urllib.parse.urlencode(params)
    data = _request_json(url, timeout=8)
    return _normalize_searx(data, limit, query=query)


def _bing_rss_search_sync(query: str, limit: int):
    params = {
        "q": query,
        "format": "rss",
        "setlang": "en-US",
        "cc": "US",
    }
    url = BING_RSS_URL + "?" + urllib.parse.urlencode(params)

    last_error = None
    xml_data = None

    for attempt in range(3):
        try:
            req = urllib.request.Request(
                url,
                headers={
                    "User-Agent": "Mozilla/5.0 (Ying Search/1.0)",
                    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.7",
                },
            )
            with urllib.request.urlopen(req, timeout=6) as resp:
                xml_data = resp.read()
            break
        except Exception as exc:
            last_error = exc
            if attempt < 2:
                time.sleep(0.7 * (attempt + 1))

    if xml_data is None:
        raise last_error or RuntimeError("bing rss unavailable")

    root = ET.fromstring(xml_data)
    output = []
    seen = set()

    for item in root.findall(".//item"):
        title = (item.findtext("title") or "").strip()
        link = (item.findtext("link") or "").strip()
        desc = (item.findtext("description") or "").strip()

        if not title or not link or link in seen:
            continue

        normalized = {
            "title": title,
            "url": link,
            "content": desc,
            "engine": "bing-rss",
            "source": "bing-rss",
        }

        if not _looks_relevant(query, normalized):
            continue

        seen.add(link)
        output.append(normalized)

        if len(output) >= limit:
            break

    return output


def _bing_news_rss_search_sync(query: str, limit: int):
    params = {
        "q": query,
        "format": "RSS",
    }
    url = BING_NEWS_RSS_URL + "?" + urllib.parse.urlencode(params)

    last_error = None
    xml_data = None
    for attempt in range(3):
        try:
            req = urllib.request.Request(
                url,
                headers={
                    "User-Agent": "Mozilla/5.0 (Ying Search/1.0)",
                    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.7",
                },
            )
            with urllib.request.urlopen(req, timeout=6) as resp:
                xml_data = resp.read()
            break
        except Exception as exc:
            last_error = exc
            if attempt < 2:
                time.sleep(0.6 * (attempt + 1))

    if xml_data is None:
        raise last_error or RuntimeError("bing news rss unavailable")

    root = ET.fromstring(xml_data)
    output = []
    seen = set()

    for item in root.findall(".//item"):
        title = (item.findtext("title") or "").strip()
        link = (item.findtext("link") or "").strip()
        desc = (item.findtext("description") or "").strip()

        if not title or not link or link in seen:
            continue

        normalized = {
            "title": title,
            "url": link,
            "content": desc,
            "engine": "bing-news-rss",
            "source": "bing-news-rss",
        }

        if not _looks_relevant(query, normalized):
            continue

        seen.add(link)
        output.append(normalized)

        if len(output) >= limit:
            break

    return output


def _search_sync(query: str, limit: int = 5):
    freshness_words = (
        "最新", "新闻", "今天", "今日", "刚刚",
        "latest", "news", "today", "breaking",
    )
    is_fresh = any(
        word.lower() in str(query).lower()
        for word in freshness_words
    )

    # 普通检索优先自己的本地 SearXNG。
    try:
        results = _searx_search_sync(query, limit)
        if results:
            return {
                "backend": "searxng",
                "results": results,
                "fallback_used": False,
            }
    except Exception:
        pass

    # 新闻 RSS 只作备用，本地检索优先。
    if is_fresh:
        try:
            results = _bing_news_rss_search_sync(query, limit)
            if results:
                return {
                    "backend": "bing-news-rss",
                    "results": results,
                    "fallback_used": True,
                }
        except Exception:
            pass


    # VPS 当前到多个搜索引擎的网页端会超时，
    # Bing RSS 端点可正常访问，因此作为独立兜底。
    try:
        results = _bing_rss_search_sync(query, limit)
        if results:
            return {
                "backend": "bing-rss",
                "results": results,
                "fallback_used": True,
            }
    except Exception:
        pass

    if not is_fresh:
        try:
            results = _bing_news_rss_search_sync(query, limit)
            if results:
                return {
                    "backend": "bing-news-rss",
                    "results": results,
                    "fallback_used": True,
                }
        except Exception:
            pass

    return {
        "backend": "unavailable",
        "results": [],
        "fallback_used": True,
        "error": "all_backends_unavailable",
    }


async def _enrich_results(results, *, max_pages=2):
    """
    对前几个搜索结果抓取少量正文。
    搜索摘要仍保留；正文抓取失败不会让整次搜索失败。
    """
    enriched = []

    for idx, item in enumerate(results):
        item = dict(item)

        if idx < max_pages:
            try:
                page = await fetch_page_text(
                    item.get("url") or "",
                    max_chars=4200,
                )
                text = str(page.get("text") or "").strip()
                if text:
                    item["page_text"] = text
                    item["fetched_url"] = page.get("url")
            except Exception:
                pass

        enriched.append(item)

    return enriched


async def web_search(query: str, limit: int = 5):
    query = str(query or "").strip()
    if not query:
        return {
            "query": "",
            "backend": "none",
            "results": [],
            "fallback_used": False,
        }

    result = await asyncio.to_thread(
        _search_sync,
        query,
        max(1, min(int(limit), 8)),
    )
    result["query"] = query

    results = result.get("results") or []
    if results:
        result["results"] = await _enrich_results(
            results,
            max_pages=2,
        )

    return result


def search_fallback_text(search_data: dict) -> str:
    """Guaranteed user-facing answer from actual results when the model fails."""
    data = search_data or {}
    if data.get("error") == "search_timeout":
        return "这次联网搜索超时了，我没拿到可靠结果。稍后再让我查一次。"
    results = data.get("results") or []
    if not results:
        return "这次没搜到可靠结果，我就不拿旧知识冒充刚查到的内容了。"
    lines = []
    for item in results[:4]:
        title = str(item.get("title") or "无标题").strip()[:100]
        content = re.sub(r"\s+", " ", str(item.get("page_text") or item.get("content") or "")).strip()[:180]
        source = str(item.get("url") or "").strip()[:450]
        lines.append(f"• {title}" + (f"：{content}" if content else "") + (f"\n  {source}" if source else ""))
    return "找到了这些结果，我先把来源发你：\n" + "\n".join(lines)
