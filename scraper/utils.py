from __future__ import annotations

import asyncio
import re
import time

import httpx
from thefuzz import fuzz

USER_AGENT = "NycTheaterDashboard/1.0 (personal project)"
REQUEST_DELAY = 1.5


def slugify(text: str) -> str:
    text = text.lower().strip()
    text = re.sub(r"[^\w\s-]", "", text)
    text = re.sub(r"[\s_]+", "-", text)
    return re.sub(r"-+", "-", text).strip("-")


def make_show_id(title: str, venue: str) -> str:
    return f"{slugify(title)}-{slugify(venue)}"


def fuzzy_match_title(title_a: str, title_b: str, threshold: int = 80) -> bool:
    return fuzz.token_sort_ratio(title_a.lower(), title_b.lower()) >= threshold


def new_client(**kwargs) -> httpx.AsyncClient:
    headers = {"User-Agent": USER_AGENT}
    if "headers" in kwargs:
        headers.update(kwargs.pop("headers"))
    return httpx.AsyncClient(
        headers=headers,
        timeout=30.0,
        follow_redirects=True,
        **kwargs,
    )


async def rate_limited_get(
    client: httpx.AsyncClient, url: str, **kwargs
) -> httpx.Response:
    await asyncio.sleep(REQUEST_DELAY)
    return await client.get(url, **kwargs)
