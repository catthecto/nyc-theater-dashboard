from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass

from bs4 import BeautifulSoup

from scraper.utils import new_client, rate_limited_get

logger = logging.getLogger(__name__)

BROADWAY_URL = "https://playbill.com/shows/broadway"
OFF_BROADWAY_URL = "https://playbill.com/shows/offbroadway"
BASE_URL = "https://playbill.com"

BROWSER_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)


@dataclass
class PlaybillShow:
    title: str
    venue: str
    category: str  # "broadway" or "off-broadway"
    production_url: str
    image_url: str | None


async def fetch_all_shows() -> list[PlaybillShow]:
    shows: list[PlaybillShow] = []
    async with new_client(headers={"User-Agent": BROWSER_UA}) as client:
        for url, category in [
            (BROADWAY_URL, "broadway"),
            (OFF_BROADWAY_URL, "off-broadway"),
        ]:
            logger.info(f"Fetching Playbill {category} shows")
            resp = await rate_limited_get(client, url)
            resp.raise_for_status()
            page_shows = _parse_listing_page(resp.text, category)
            shows.extend(page_shows)
            logger.info(f"Found {len(page_shows)} {category} shows on Playbill")
    return shows


def _parse_listing_page(html: str, category: str) -> list[PlaybillShow]:
    soup = BeautifulSoup(html, "html.parser")
    shows: list[PlaybillShow] = []

    for article in soup.find_all("article"):
        title_tag = article.find("h3")
        if not title_tag:
            continue

        link = title_tag.find("a")
        if not link:
            continue

        dl_data = link.get("data-dl-data", "")
        try:
            dl_json = json.loads(dl_data)
            title = dl_json.get("show_name", link.get_text(strip=True))
        except (json.JSONDecodeError, TypeError):
            title = link.get_text(strip=True)

        href = link.get("href", "")
        production_url = BASE_URL + href if href.startswith("/") else href

        venue = ""
        venue_list = article.find("ul")
        if venue_list:
            venue_li = venue_list.find("li")
            if venue_li:
                venue = venue_li.get_text(strip=True)

        image_url = None
        figures = article.find_all("figure")
        for fig in figures:
            img = fig.find("img")
            if img and img.get("src"):
                src = img["src"]
                if src.startswith("//"):
                    src = "https:" + src
                if "editorial" in src or "deco" in src:
                    image_url = src
                    break

        if not title:
            continue

        shows.append(
            PlaybillShow(
                title=title,
                venue=venue,
                category=category,
                production_url=production_url,
                image_url=image_url,
            )
        )

    return shows
