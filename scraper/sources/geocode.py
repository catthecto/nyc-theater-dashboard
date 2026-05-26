from __future__ import annotations

import asyncio
import json
import logging
from pathlib import Path

import re

from scraper.utils import new_client

logger = logging.getLogger(__name__)

_NOT_A_VENUE = re.compile(r"^(Closes|Opens|Begins|In Previews)", re.IGNORECASE)

NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
CACHE_PATH = Path(__file__).resolve().parent.parent.parent / ".geocode-cache.json"


def _load_cache() -> dict[str, list[float]]:
    if CACHE_PATH.exists():
        return json.loads(CACHE_PATH.read_text())
    return {}


def _save_cache(cache: dict[str, list[float]]) -> None:
    CACHE_PATH.write_text(json.dumps(cache, indent=2))


async def geocode_venues(venue_names: list[str]) -> dict[str, tuple[float, float]]:
    cache = _load_cache()
    results: dict[str, tuple[float, float]] = {}
    to_fetch: list[str] = []

    for name in set(venue_names):
        if not name or _NOT_A_VENUE.match(name):
            continue
        if name in cache:
            if cache[name]:
                results[name] = tuple(cache[name])
        else:
            to_fetch.append(name)

    if to_fetch:
        logger.info(f"Geocoding {len(to_fetch)} new venues ({len(results)} cached)")
        async with new_client() as client:
            for venue in to_fetch:
                query = f"{venue}, New York, NY"
                try:
                    await asyncio.sleep(1.1)
                    resp = await client.get(
                        NOMINATIM_URL,
                        params={
                            "q": query,
                            "format": "json",
                            "limit": 1,
                            "viewbox": "-74.05,40.90,-73.85,40.65",
                            "bounded": 1,
                        },
                    )
                    resp.raise_for_status()
                    data = resp.json()
                    if data:
                        lat = float(data[0]["lat"])
                        lon = float(data[0]["lon"])
                        if 40.65 <= lat <= 40.90 and -74.05 <= lon <= -73.85:
                            results[venue] = (lat, lon)
                            cache[venue] = [lat, lon]
                        else:
                            logger.warning(f"Geocode result for '{venue}' outside NYC: {lat},{lon}")
                            cache[venue] = []
                except Exception as e:
                    logger.warning(f"Failed to geocode '{venue}': {e}")

        _save_cache(cache)

    logger.info(f"Geocoded {len(results)}/{len(set(venue_names))} venues")
    return results
