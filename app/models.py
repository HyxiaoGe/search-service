from enum import StrEnum

from pydantic import BaseModel, Field


class SearchType(StrEnum):
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
    content: str | None = None  # 网页正文摘要（Tavily 等 provider 支持）
    favicon: str | None = None  # 网站 favicon URL
    published_at: str | None = None


class SearchResponse(BaseModel):
    query: str
    type: SearchType
    provider: str
    cached: bool = False
    results: list[SearchResultItem] = []
