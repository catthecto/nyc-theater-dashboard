from __future__ import annotations

import asyncio
import logging
import re
from dataclasses import dataclass
from datetime import date, datetime

from bs4 import BeautifulSoup

from scraper.utils import new_client, rate_limited_get

logger = logging.getLogger(__name__)

BASE_URL = "https://www.theatermania.com"
LISTING_URLS = {
    "broadway": f"{BASE_URL}/shows/new-york-city/broadway",
    "off-broadway": f"{BASE_URL}/shows/new-york-city/off-broadway",
    "off-off-broadway": f"{BASE_URL}/shows/new-york-city/off-off-broadway",
}

EXCLUDED_GENRE_KEYWORDS = {"comedy", "stand-up", "sketch", "concert", "magic"}

BROWSER_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)


@dataclass
class TheaterManiaShow:
    title: str
    venue: str
    category: str
    genre: str
    opening_date: date | None
    closing_date: date | None
    description: str
    image_url: str | None
    detail_url: str
    ticket_url: str | None


def _parse_date(text: str) -> date | None:
    text = text.strip().rstrip(".")
    for fmt in ("%B %d, %Y", "%b %d, %Y"):
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    return None


def _parse_listing_card(card, category: str) -> tuple[str, str, str, str | None, str | None] | None:
    h5 = card.find("h5")
    if not h5:
        return None
    title = h5.get_text(strip=True)
    if title in ("SUBSCRIBE", "Filter & Sort"):
        return None

    link = h5.parent
    href = link.get("href", "") if link.name == "a" else ""
    if not href:
        return None

    h6 = card.find("h6")
    genre = h6.get_text(strip=True).lower() if h6 else ""
    if any(kw in genre for kw in EXCLUDED_GENRE_KEYWORDS):
        return None

    texts = [t.strip() for t in card.stripped_strings]
    opening = None
    closing = None
    for t in texts:
        if t.startswith("Performances begin:") or t.startswith("Opening Night:"):
            opening = t.split(":", 1)[1].strip()
        elif t.startswith("Final performance:") or t.startswith("Closing Night:"):
            closing = t.split(":", 1)[1].strip()

    return title, href, genre, opening, closing


async def _fetch_detail(client, url: str) -> dict:
    try:
        await asyncio.sleep(1.0)
        resp = await rate_limited_get(client, url)
        resp.raise_for_status()
    except Exception as e:
        logger.warning(f"Failed to fetch detail {url}: {e}")
        return {}

    soup = BeautifulSoup(resp.text, "html.parser")
    result: dict = {}

    venue_div = soup.find("div", class_="block-detail")
    if venue_div:
        parts = [t.strip() for t in venue_div.stripped_strings if t.strip() not in (",", "View Map")]
        if parts:
            result["venue"] = parts[0]

    dates_div = soup.find("div", class_="dates-section")
    if dates_div:
        text = dates_div.get_text(" ", strip=True)
        opening_match = re.search(r"Opening Night:\s*(.+?)(?:\s*\||\s*Closing|$)", text)
        closing_match = re.search(r"Closing Night:\s*(.+?)(?:\s*\||$)", text)
        if opening_match:
            result["opening_date"] = _parse_date(opening_match.group(1))
        if closing_match:
            result["closing_date"] = _parse_date(closing_match.group(1))

    about = soup.find("h2", string=lambda s: s and "About" in s)
    if about:
        desc_el = about.find_next_sibling()
        if desc_el:
            result["description"] = desc_el.get_text(strip=True)

    og_img = soup.find("meta", property="og:image")
    if og_img:
        result["image_url"] = og_img.get("content")

    for a in soup.find_all("a", href=True):
        text = a.get_text(strip=True).lower()
        href = a["href"]
        if "buy ticket" in text and "theatermania.com/info" not in href:
            result["ticket_url"] = href
            break

    return result


async def fetch_all_shows() -> list[TheaterManiaShow]:
    shows: list[TheaterManiaShow] = []
    listings: list[tuple[str, str, str, str | None, str | None]] = []

    async with new_client(headers={"User-Agent": BROWSER_UA}) as client:
        for category, url in LISTING_URLS.items():
            logger.info(f"Fetching TheaterMania {category} listings")
            try:
                resp = await rate_limited_get(client, url)
                resp.raise_for_status()
            except Exception as e:
                logger.warning(f"Failed to fetch {url}: {e}")
                continue

            soup = BeautifulSoup(resp.text, "html.parser")
            cards = soup.find_all("div", class_="card-body")
            count = 0
            for card in cards:
                parsed = _parse_listing_card(card, category)
                if parsed:
                    listings.append((*parsed[:3], parsed[3], parsed[4]))
                    count += 1
            logger.info(f"Found {count} {category} shows on TheaterMania")

        logger.info(f"Fetching details for {len(listings)} TheaterMania shows")
        for title, detail_url, genre, list_opening, list_closing in listings:
            detail = await _fetch_detail(client, detail_url)

            venue = detail.get("venue", "")
            opening = detail.get("opening_date") or (_parse_date(list_opening) if list_opening else None)
            closing = detail.get("closing_date") or (_parse_date(list_closing) if list_closing else None)

            cat_path = detail_url.split("/")
            category = "broadway"
            if "off-off-broadway" in cat_path:
                category = "off-off-broadway"
            elif "off-broadway" in cat_path:
                category = "off-broadway"

            shows.append(
                TheaterManiaShow(
                    title=title,
                    venue=venue,
                    category=category,
                    genre=genre,
                    opening_date=opening,
                    closing_date=closing,
                    description=detail.get("description", ""),
                    image_url=detail.get("image_url"),
                    detail_url=detail_url,
                    ticket_url=detail.get("ticket_url"),
                )
            )

    logger.info(f"Fetched {len(shows)} total shows from TheaterMania")
    return shows
