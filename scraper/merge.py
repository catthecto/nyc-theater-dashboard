from __future__ import annotations

import logging
import re
from collections import defaultdict
from datetime import date, datetime, timezone

from scraper.schema import Category, DataFile, Metadata, Price, Review, Show, Status
from scraper.sources.playbill import PlaybillShow
from scraper.sources.todaytix import TodayTixShow
from scraper.utils import fuzzy_match_title, make_show_id

logger = logging.getLogger(__name__)

GENRE_MAP = {
    "musicals": "musical",
    "plays": "play",
    "comedy": "comedy",
    "drama": "drama",
    "circus and magic": "experience",
    "dance": "dance",
    "opera": "opera",
    "concerts": "concert",
    "family friendly": "family",
    "immersive": "immersive",
}

EXCLUDED_GENRES = {
    "gift cards",
    "films",
    "comedy shows",
    "museums and galleries",
    "tours",
    "gardens",
}


def merge_sources(
    todaytix_shows: list[TodayTixShow],
    playbill_shows: list[PlaybillShow],
    venue_coords: dict[str, tuple[float, float]] | None = None,
) -> DataFile:
    venue_coords = venue_coords or {}
    filtered = [tt for tt in todaytix_shows if tt.category_name.lower() not in EXCLUDED_GENRES]
    deduped = _dedup_todaytix(filtered)

    playbill_by_title: dict[str, PlaybillShow] = {}
    for ps in playbill_shows:
        playbill_by_title[ps.title.lower().strip()] = ps

    shows: list[Show] = []
    seen_ids: set[str] = set()

    for tt in deduped:

        pb = _find_playbill_match(tt, playbill_by_title)

        if pb:
            category = Category(pb.category)
        elif tt.is_broadway:
            category = Category.BROADWAY
        else:
            category = Category.OFF_BROADWAY

        show_id = make_show_id(tt.title, tt.venue)
        if show_id in seen_ids:
            continue
        seen_ids.add(show_id)

        price = None
        if tt.cheapest_price is not None:
            price = Price(
                cheapest=tt.cheapest_price,
                currency=tt.currency,
                source="todaytix",
                as_of=date.today(),
            )

        opening_date = None
        if tt.start_date:
            try:
                opening_date = date.fromisoformat(tt.start_date)
            except ValueError:
                pass

        closing_date = None
        if tt.end_date:
            try:
                closing_date = date.fromisoformat(tt.end_date)
            except ValueError:
                pass

        status = _determine_status(opening_date)
        genre = GENRE_MAP.get(tt.category_name.lower(), tt.category_name.lower())

        tags = [s for s in tt.subcategories if s not in ("broadway", "off-broadway")]
        if tt.rush_text:
            tags.append("rush-available")

        image_url = tt.image_url
        if pb and pb.image_url and not image_url:
            image_url = pb.image_url

        playbill_url = pb.production_url if pb else None
        todaytix_url = f"https://www.todaytix.com/shows/{tt.id}"

        review = None
        if tt.review_score is not None and tt.review_count:
            review = Review(
                score=tt.review_score,
                review_count=tt.review_count,
                adjectives=tt.review_adjectives,
            )

        coords = venue_coords.get(tt.venue)
        lat, lng = (coords[0], coords[1]) if coords else (None, None)

        shows.append(
            Show(
                id=show_id,
                title=tt.title,
                venue=tt.venue,
                category=category,
                status=status,
                genre=genre,
                opening_date=opening_date,
                closing_date=closing_date,
                description=tt.description or None,
                image_url=image_url,
                playbill_url=playbill_url,
                todaytix_url=todaytix_url,
                price=price,
                review=review,
                lat=lat,
                lng=lng,
                tags=tags,
            )
        )

    for pb in playbill_shows:
        test_id = make_show_id(pb.title, pb.venue)
        if test_id in seen_ids:
            continue

        already_matched = any(
            fuzzy_match_title(pb.title, s.title) for s in shows
        )
        if already_matched:
            continue

        seen_ids.add(test_id)
        coords = venue_coords.get(pb.venue)
        lat, lng = (coords[0], coords[1]) if coords else (None, None)
        shows.append(
            Show(
                id=test_id,
                title=pb.title,
                venue=pb.venue,
                category=Category(pb.category),
                status=Status.RUNNING,
                playbill_url=pb.production_url,
                image_url=pb.image_url,
                lat=lat,
                lng=lng,
            )
        )

    before = len(shows)
    shows = [s for s in shows if s.price or s.description or s.review]
    logger.info(f"Dropped {before - len(shows)} shows with no price, description, or reviews")

    sources = ["todaytix"]
    if playbill_shows:
        sources.append("playbill")

    logger.info(f"Merged {len(shows)} total shows")

    return DataFile(
        metadata=Metadata(
            last_updated=datetime.now(timezone.utc),
            show_count=len(shows),
            sources=sources,
        ),
        shows=shows,
    )


LOTTERY_PREFIX_RE = re.compile(
    r"^(Standard Lottery|Senior \d+\+ Lottery|ADA Accessible Lottery|Grown-Up Nights?!?)\s*[-–—]?\s*",
    re.IGNORECASE,
)


def _normalize_title(title: str) -> str:
    return LOTTERY_PREFIX_RE.sub("", title).strip()


def _dedup_todaytix(shows: list[TodayTixShow]) -> list[TodayTixShow]:
    by_venue: dict[str, list[TodayTixShow]] = defaultdict(list)
    for s in shows:
        by_venue[s.venue.lower().strip()].append(s)

    result: list[TodayTixShow] = []
    for venue_shows in by_venue.values():
        merged_indices: set[int] = set()
        for i, a in enumerate(venue_shows):
            if i in merged_indices:
                continue
            best = a
            norm_a = _normalize_title(a.title)
            for j, b in enumerate(venue_shows):
                if j <= i or j in merged_indices:
                    continue
                norm_b = _normalize_title(b.title)
                if not fuzzy_match_title(norm_a, norm_b, threshold=80):
                    continue
                merged_indices.add(j)
                best = _pick_best(best, b)
            result.append(best)

    logger.info(f"Deduped TodayTix: {len(shows)} -> {len(result)} shows")
    return result


def _pick_best(a: TodayTixShow, b: TodayTixShow) -> TodayTixShow:
    title = a.title if len(_normalize_title(a.title)) <= len(_normalize_title(b.title)) else b.title
    title = _normalize_title(title)

    end_a = a.end_date or ""
    end_b = b.end_date or ""
    end_date = max(end_a, end_b) or None

    price = None
    if a.cheapest_price is not None and b.cheapest_price is not None:
        price = min(a.cheapest_price, b.cheapest_price)
    elif a.cheapest_price is not None:
        price = a.cheapest_price
    elif b.cheapest_price is not None:
        price = b.cheapest_price

    primary = a if (a.image_url and a.description) else b

    review_a = (a.review_score or 0, a.review_count or 0)
    review_b = (b.review_score or 0, b.review_count or 0)
    review_source = a if review_a >= review_b else b

    return TodayTixShow(
        id=primary.id,
        title=title,
        venue=primary.venue,
        cheapest_price=price,
        currency=primary.currency,
        category_name=primary.category_name,
        subcategories=list(set(a.subcategories + b.subcategories)),
        description=primary.description or a.description or b.description,
        image_url=primary.image_url or a.image_url or b.image_url,
        start_date=min(a.start_date or "", b.start_date or "") or None,
        end_date=end_date,
        rush_text=a.rush_text or b.rush_text,
        is_broadway=a.is_broadway or b.is_broadway,
        review_score=review_source.review_score,
        review_count=review_source.review_count,
        review_adjectives=review_source.review_adjectives,
    )


def _find_playbill_match(
    tt: TodayTixShow, playbill_map: dict[str, PlaybillShow]
) -> PlaybillShow | None:
    key = tt.title.lower().strip()
    if key in playbill_map:
        return playbill_map[key]

    for pb_title, pb in playbill_map.items():
        if fuzzy_match_title(tt.title, pb.title):
            return pb

    return None


def _determine_status(opening_date: date | None) -> Status:
    if opening_date is None:
        return Status.RUNNING
    today = date.today()
    if opening_date > today:
        return Status.UPCOMING
    return Status.RUNNING
