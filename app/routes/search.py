from fastapi import APIRouter, Request

from app.cache import get_cached, set_cached
from app.limiter import limiter
from app.logger import get_logger
from app.models import SearchRequest, SearchResponse
from app.providers.registry import get_provider

router = APIRouter()
log = get_logger()


@router.post("/search", response_model=SearchResponse)
@limiter.limit("10/second")
async def search(request: Request, body: SearchRequest) -> SearchResponse:
    provider_name = body.provider or None
    provider = get_provider(provider_name)
    actual_provider = provider_name or "brave"

    cached = await get_cached(actual_provider, body.type, body.query, body.lang, body.region)
    if cached:
        log.info("cache_hit", query=body.query, type=body.type.value, provider=actual_provider)
        return cached

    log.info("search_request", query=body.query, type=body.type.value, provider=actual_provider)
    result = await provider.search(body)

    await set_cached(actual_provider, body.type, body.query, body.lang, body.region, result)
    return result
