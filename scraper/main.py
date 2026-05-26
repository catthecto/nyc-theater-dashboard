from __future__ import annotations

import asyncio
import json
import logging
import sys
from pathlib import Path

from scraper.merge import merge_sources
from scraper.sources import geocode, playbill, todaytix

OUTPUT_PATH = Path(__file__).resolve().parent.parent / "docs" / "data" / "shows.json"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)


async def run() -> None:
    logger.info("Starting data pipeline")

    todaytix_shows, playbill_shows = await asyncio.gather(
        todaytix.fetch_all_shows(),
        playbill.fetch_all_shows(),
    )

    all_venues = [s.venue for s in todaytix_shows] + [s.venue for s in playbill_shows]
    venue_coords = await geocode.geocode_venues(all_venues)

    data_file = merge_sources(todaytix_shows, playbill_shows, venue_coords)

    assert data_file.metadata.show_count >= 20, (
        f"Only {data_file.metadata.show_count} shows found — something is wrong"
    )

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(
        data_file.model_dump_json(indent=2, exclude_none=True),
        encoding="utf-8",
    )
    logger.info(f"Wrote {data_file.metadata.show_count} shows to {OUTPUT_PATH}")


def main() -> None:
    try:
        asyncio.run(run())
    except Exception:
        logger.exception("Pipeline failed")
        sys.exit(1)


if __name__ == "__main__":
    main()
