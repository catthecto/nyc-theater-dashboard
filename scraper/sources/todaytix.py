from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from datetime import date

from scraper.utils import new_client

logger = logging.getLogger(__name__)

SHOWS_URL = "https://api.todaytix.com/api/v2/shows"
NYC_LOCATION_ID = 1
PAGE_SIZE = 40


@dataclass
class TodayTixShow:
    id: int
    title: str
    venue: str
    cheapest_price: int | None
    currency: str
    category_name: str
    subcategories: list[str]
    description: str
    image_url: str | None
    start_date: str | None
    end_date: str | None
    rush_text: str | None
    is_broadway: bool
    review_score: int | None
    review_count: int | None
    review_adjectives: list[str]


async def fetch_all_shows() -> list[TodayTixShow]:
    shows: list[TodayTixShow] = []
    offset = 0

    async with new_client() as client:
        while True:
            logger.info(f"Fetching TodayTix shows offset={offset}")
            resp = await client.get(
                SHOWS_URL,
                params={
                    "location": NYC_LOCATION_ID,
                    "limit": PAGE_SIZE,
                    "offset": offset,
                },
            )
            resp.raise_for_status()
            data = resp.json()

            for raw in data.get("data", []):
                shows.append(_parse_show(raw))

            pagination = data.get("pagination", {})
            total = pagination.get("total", 0)
            offset += PAGE_SIZE
            if offset >= total:
                break

            await asyncio.sleep(1.0)

    logger.info(f"Fetched {len(shows)} shows from TodayTix")
    return shows


def _parse_show(raw: dict) -> TodayTixShow:
    subcats = [s["slug"] for s in raw.get("subcategories", []) if "slug" in s]
    is_broadway = "broadway" in subcats

    price_info = raw.get("lowPriceFaceValue") or raw.get("lowPriceForRegularTickets")
    cheapest = int(price_info["value"]) if price_info and price_info.get("value") else None
    currency = price_info["currency"] if price_info else "USD"

    image_url = raw.get("posterImageUrl") or raw.get("heroImageUrl")
    if image_url and image_url.startswith("//"):
        image_url = "https:" + image_url

    end_date = raw.get("endDate")
    if end_date == "null" or not end_date:
        end_date = None

    review = raw.get("reviewSummary") or {}
    review_score = review.get("score")
    review_count = review.get("reviewsCount")
    review_adjectives = review.get("adjectives") or []

    return TodayTixShow(
        id=raw["id"],
        title=raw.get("displayName") or raw.get("showName", ""),
        venue=raw.get("venue", ""),
        cheapest_price=cheapest,
        currency=currency,
        category_name=raw.get("category", {}).get("name", ""),
        subcategories=subcats,
        description=raw.get("description", ""),
        image_url=image_url,
        start_date=raw.get("startDate"),
        end_date=end_date,
        rush_text=raw.get("rushBannerText"),
        is_broadway=is_broadway,
        review_score=review_score,
        review_count=review_count,
        review_adjectives=review_adjectives,
    )
