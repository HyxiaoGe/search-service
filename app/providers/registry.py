from app.config import settings
from app.providers.base import SearchProvider
from app.providers.brave import BraveProvider
from app.providers.tavily import TavilyProvider

_providers: dict[str, SearchProvider] = {}


def _init_providers() -> None:
    _providers["brave"] = BraveProvider()
    if settings.TAVILY_API_KEY:
        _providers["tavily"] = TavilyProvider()


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
    return [
        {"name": name, "available": True}
        for name in _providers
    ]
