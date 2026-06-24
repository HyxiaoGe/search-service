import httpx

from app.config import settings
from app.models import (
    ProviderHistoricalUsageResponse,
    ProviderUsagePeriod,
    ProviderUsageResponse,
    SearchRequest,
    SearchResponse,
    SearchResultItem,
    SearchType,
)

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


class FirecrawlUsageError(Exception):
    pass


class FirecrawlUsageClient:
    def __init__(self) -> None:
        self.api_key = settings.FIRECRAWL_API_KEY
        self.base_url = settings.FIRECRAWL_API_URL.rstrip("/")
        self.usage_url = f"{self.base_url}/v2/team/credit-usage"
        self.historical_usage_url = f"{self.usage_url}/historical"

    async def get_usage(self) -> ProviderUsageResponse:
        payload = await self._get_json(self.usage_url)

        if not payload.get("success", False):
            raise FirecrawlUsageError("Firecrawl usage request failed")

        data = payload.get("data", {})
        if not isinstance(data, dict):
            raise FirecrawlUsageError("Firecrawl usage request failed")

        remaining_credits = self._optional_int(data.get("remainingCredits"))
        plan_credits = self._optional_int(data.get("planCredits"))
        used_credits, usage_ratio = self._calculate_usage(remaining_credits, plan_credits)

        return ProviderUsageResponse(
            provider="firecrawl",
            available=True,
            remaining_credits=remaining_credits,
            plan_credits=plan_credits,
            used_credits=used_credits,
            usage_ratio=usage_ratio,
            billing_period_start=data.get("billingPeriodStart"),
            billing_period_end=data.get("billingPeriodEnd"),
        )

    async def get_historical_usage(self, *, by_api_key: bool = False) -> ProviderHistoricalUsageResponse:
        params = {"byApiKey": "true"} if by_api_key else None
        payload = await self._get_json(self.historical_usage_url, params=params)

        if not payload.get("success", False):
            raise FirecrawlUsageError("Firecrawl usage request failed")

        raw_periods = payload.get("periods", [])
        if not isinstance(raw_periods, list):
            raise FirecrawlUsageError("Firecrawl usage request failed")

        periods = [self._parse_period(period) for period in raw_periods if isinstance(period, dict)]
        return ProviderHistoricalUsageResponse(
            provider="firecrawl",
            available=True,
            by_api_key=by_api_key,
            periods=periods,
        )

    async def _get_json(self, url: str, *, params: dict | None = None) -> dict:
        try:
            async with httpx.AsyncClient(timeout=20) as client:
                request_kwargs = {"headers": {"Authorization": f"Bearer {self.api_key}"}}
                if params is not None:
                    request_kwargs["params"] = params
                resp = await client.get(
                    url,
                    **request_kwargs,
                )
                resp.raise_for_status()
                payload = resp.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise FirecrawlUsageError("Firecrawl usage request failed") from exc
        if not isinstance(payload, dict):
            raise FirecrawlUsageError("Firecrawl usage request failed")
        return payload

    def _parse_period(self, period: dict) -> ProviderUsagePeriod:
        return ProviderUsagePeriod(
            start_date=str(period.get("startDate", "")),
            end_date=str(period.get("endDate", "")),
            api_key=self._mask_api_key(period.get("apiKey")),
            total_credits=self._required_int(period.get("totalCredits")),
        )

    def _mask_api_key(self, value: object) -> str | None:
        if not isinstance(value, str) or not value:
            return None
        if len(value) <= 10:
            return "***"
        return f"{value[:6]}...{value[-4:]}"

    def _optional_int(self, value: object) -> int | None:
        if value is None:
            return None
        try:
            return int(value)
        except (TypeError, ValueError) as exc:
            raise FirecrawlUsageError("Firecrawl usage request failed") from exc

    def _required_int(self, value: object) -> int:
        try:
            return int(value)
        except (TypeError, ValueError) as exc:
            raise FirecrawlUsageError("Firecrawl usage request failed") from exc

    def _calculate_usage(
        self, remaining_credits: int | None, plan_credits: int | None
    ) -> tuple[int | None, float | None]:
        if remaining_credits is None or plan_credits is None:
            return None, None
        if remaining_credits > plan_credits:
            return None, None

        used_credits = plan_credits - remaining_credits
        if plan_credits <= 0:
            return used_credits, None
        return used_credits, used_credits / plan_credits
