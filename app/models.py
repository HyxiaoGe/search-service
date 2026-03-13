from enum import Enum

from pydantic import BaseModel, Field


class SearchType(str, Enum):
    WEB = "web"
    NEWS = "news"
    IMAGE = "image"


class SearchRequest(BaseModel):
    query: str
    type: SearchType = SearchType.WEB
    provider: str | None = None
    count: int = Field(default=10, ge=1, le=50)
    page: int = Field(default=1, ge=1)
    lang: str = "en"
    region: str = "us"
    freshness: str | None = None


class SearchResultItem(BaseModel):
    title: str
    url: str
    description: str
    published_at: str | None = None


class SearchResponse(BaseModel):
    query: str
    type: SearchType
    provider: str
    cached: bool = False
    results: list[SearchResultItem] = []
