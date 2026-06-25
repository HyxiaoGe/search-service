from app.config import settings
from app.models import ProviderHistoricalUsageResponse, ProviderUsageResponse
from app.providers.base import SearchProvider
from app.providers.brave import BraveProvider
from app.providers.firecrawl import FirecrawlProvider, FirecrawlUsageClient, FirecrawlUsageError
from app.providers.tavily import TavilyProvider
from app.usage import get_recorded_provider_usage

_providers: dict[str, SearchProvider] = {}


class ProviderUsageError(Exception):
    pass


def _init_providers() -> None:
    _providers["brave"] = BraveProvider()
    if settings.TAVILY_API_KEY:
        _providers["tavily"] = TavilyProvider()
    if settings.FIRECRAWL_API_KEY:
        _providers["firecrawl"] = FirecrawlProvider()


def get_provider(name: str | None = None) -> SearchProvider:
    if not _providers:
        _init_providers()
    provider_name = name or settings.SEARCH_PROVIDER
    if provider_name not in _providers:
        raise ValueError(f"Unknown provider: {provider_name}")
    return _providers[provider_name]


def get_fallback_provider(primary_name: str) -> tuple[str | None, SearchProvider | None]:
    """获取备用 provider（排除主 provider）"""
    if not _providers:
        _init_providers()
    for name, prov in _providers.items():
        if name != primary_name:
            return name, prov
    return None, None


def list_providers() -> list[dict]:
    if not _providers:
        _init_providers()
    return [{"name": name, "available": True} for name in _providers]


async def get_firecrawl_usage() -> ProviderUsageResponse:
    if not settings.FIRECRAWL_API_KEY.strip():
        return ProviderUsageResponse(provider="firecrawl", available=False)

    try:
        usage = await FirecrawlUsageClient().get_usage()
    except FirecrawlUsageError as exc:
        raise ProviderUsageError(str(exc)) from exc

    usage.recorded_usage = await get_recorded_provider_usage(
        "firecrawl",
        period_start=usage.billing_period_start,
        period_end=usage.billing_period_end,
    )
    return usage


async def get_firecrawl_historical_usage(*, by_api_key: bool = False) -> ProviderHistoricalUsageResponse:
    if not settings.FIRECRAWL_API_KEY.strip():
        return ProviderHistoricalUsageResponse(provider="firecrawl", available=False, by_api_key=by_api_key)

    try:
        return await FirecrawlUsageClient().get_historical_usage(by_api_key=by_api_key)
    except FirecrawlUsageError as exc:
        raise ProviderUsageError(str(exc)) from exc
