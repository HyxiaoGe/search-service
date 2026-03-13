import hashlib
import json

import redis.asyncio as redis

from app.config import settings
from app.models import SearchResponse, SearchType

_redis: redis.Redis | None = None


async def get_redis() -> redis.Redis:
    global _redis
    if _redis is None:
        _redis = redis.from_url(settings.REDIS_URL, decode_responses=True)
    return _redis


async def close_redis() -> None:
    global _redis
    if _redis is not None:
        await _redis.aclose()
        _redis = None


def _cache_key(provider: str, search_type: str, query: str, lang: str, region: str) -> str:
    raw = f"{provider}:{search_type}:{query.lower().strip()}:{lang}:{region}"
    return f"search:{hashlib.sha256(raw.encode()).hexdigest()}"


def _ttl_for_type(search_type: SearchType) -> int:
    return {
        SearchType.WEB: settings.CACHE_TTL_WEB,
        SearchType.NEWS: settings.CACHE_TTL_NEWS,
        SearchType.IMAGE: settings.CACHE_TTL_IMAGE,
    }[search_type]


async def get_cached(
    provider: str, search_type: SearchType, query: str, lang: str, region: str
) -> SearchResponse | None:
    r = await get_redis()
    key = _cache_key(provider, search_type.value, query, lang, region)
    data = await r.get(key)
    if data is None:
        return None
    resp = SearchResponse.model_validate_json(data)
    resp.cached = True
    return resp


async def set_cached(
    provider: str, search_type: SearchType, query: str, lang: str, region: str,
    response: SearchResponse,
) -> None:
    r = await get_redis()
    key = _cache_key(provider, search_type.value, query, lang, region)
    ttl = _ttl_for_type(search_type)
    await r.setex(key, ttl, response.model_dump_json())


async def flush_cache() -> int:
    r = await get_redis()
    keys = [k async for k in r.scan_iter("search:*")]
    if keys:
        await r.delete(*keys)
    return len(keys)
