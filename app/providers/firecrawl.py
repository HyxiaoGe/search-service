import httpx

from app.config import settings
from app.models import SearchRequest, SearchResponse, SearchResultItem, SearchType

FIRECRAWL_SOURCES = {
    SearchType.WEB: "web",
    SearchType.NEWS: "news",
    SearchType.IMAGE: "images",
}

FIRECRAWL_RESULT_KEYS = {
    SearchType.WEB: "web",
    SearchType.NEWS: "news",
    SearchType.IMAGE: "images",
}

FRESHNESS_TBS = {
    "pd": "qdr:d",
    "pw": "qdr:w",
    "pm": "qdr:m",
    "py": "qdr:y",
}


class FirecrawlProvider:
    def __init__(self) -> None:
        self.api_key = settings.FIRECRAWL_API_KEY
        self.search_url = f"{settings.FIRECRAWL_API_URL.rstrip('/')}/v2/search"

    async def search(self, request: SearchRequest) -> SearchResponse:
        payload = self._build_payload(request)
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        async with httpx.AsyncClient(timeout=20) as client:
            resp = await client.post(self.search_url, json=payload, headers=headers)
            resp.raise_for_status()
            data = resp.json()

        return SearchResponse(
            query=request.query,
            type=request.type,
            provider="firecrawl",
            cached=False,
            results=self._parse_results(data, request.type),
        )

    def _build_payload(self, request: SearchRequest) -> dict:
        payload: dict = {
            "query": request.query,
            "limit": request.count,
            "sources": [FIRECRAWL_SOURCES[request.type]],
        }

        if request.region:
            payload["country"] = request.region.upper()
        if request.freshness:
            payload["tbs"] = FRESHNESS_TBS.get(request.freshness, request.freshness)
        if request.domain_filters:
            payload["includeDomains"] = request.domain_filters

        return payload

    def _parse_results(self, data: dict, search_type: SearchType) -> list[SearchResultItem]:
        if search_type == SearchType.IMAGE:
            return self._parse_image_results(data)
        return self._parse_text_results(data, search_type)

    def _items_for_type(self, data: dict, search_type: SearchType) -> list[dict]:
        container = data.get("data", {})
        items = container.get(FIRECRAWL_RESULT_KEYS[search_type], [])
        if isinstance(items, list):
            return items
        return []

    def _parse_text_results(self, data: dict, search_type: SearchType) -> list[SearchResultItem]:
        items: list[SearchResultItem] = []
        for r in self._items_for_type(data, search_type):
            description = r.get("description") or r.get("snippet") or ""
            items.append(
                SearchResultItem(
                    title=r.get("title", ""),
                    url=r.get("url", ""),
                    description=description,
                    content=r.get("markdown") or description,
                    published_at=self._published_at(r),
                    favicon=r.get("favicon"),
                )
            )
        return items

    def _parse_image_results(self, data: dict) -> list[SearchResultItem]:
        items: list[SearchResultItem] = []
        for r in self._items_for_type(data, SearchType.IMAGE):
            items.append(
                SearchResultItem(
                    title=r.get("title", ""),
                    url=r.get("imageUrl", ""),
                    description=r.get("url") or r.get("pageUrl") or "",
                )
            )
        return items

    def _published_at(self, item: dict) -> str | None:
        return item.get("published_at") or item.get("publishedDate") or item.get("published_date") or item.get("date")
