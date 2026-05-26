from __future__ import annotations

from datetime import date, datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class Category(str, Enum):
    BROADWAY = "broadway"
    OFF_BROADWAY = "off-broadway"


class Status(str, Enum):
    RUNNING = "running"
    PREVIEWS = "previews"
    UPCOMING = "upcoming"


class Price(BaseModel):
    cheapest: int
    currency: str = "USD"
    source: str
    as_of: date


class Review(BaseModel):
    score: int
    review_count: int
    adjectives: list[str] = Field(default_factory=list)


class Show(BaseModel):
    id: str
    title: str
    venue: str
    category: Category
    status: Status = Status.RUNNING
    genre: Optional[str] = None
    opening_date: Optional[date] = None
    closing_date: Optional[date] = None
    description: Optional[str] = None
    image_url: Optional[str] = None
    playbill_url: Optional[str] = None
    todaytix_url: Optional[str] = None
    price: Optional[Price] = None
    review: Optional[Review] = None
    lat: Optional[float] = None
    lng: Optional[float] = None
    tags: list[str] = Field(default_factory=list)


class Metadata(BaseModel):
    last_updated: datetime
    show_count: int
    sources: list[str]


class DataFile(BaseModel):
    metadata: Metadata
    shows: list[Show]
