from fastapi import APIRouter, Request

from app.cache import get_cached, set_cached
from app.config import settings
from app.limiter import limiter
from app.logger import get_logger
from app.models import SearchRequest, SearchResponse
from app.providers.registry import get_fallback_provider, get_provider

router = APIRouter()
log = get_logger()


@router.post("/search", response_model=SearchResponse)
@limiter.limit("10/second")
async def search(request: Request, body: SearchRequest) -> SearchResponse:
    provider_name = body.provider or None
    provider = get_provider(provider_name)
    actual_provider = provider_name or settings.SEARCH_PROVIDER

    cached = await get_cached(actual_provider, body.type, body.query, body.lang, body.region)
    if cached:
        log.info("cache_hit", query=body.query, type=body.type.value, provider=actual_provider)
        return cached

    log.info("search_request", query=body.query, type=body.type.value, provider=actual_provider)
    result = await provider.search(body)
    log.info(
        "search_response",
        query=body.query,
        provider=actual_provider,
        result_count=len(result.results),
        titles=[r.title[:50] for r in result.results[:3]],
    )

    # 结果不足时尝试 fallback provider
    min_acceptable = max(body.count // 2, 1)
    if len(result.results) < min_acceptable:
        fb_name, fb_provider = get_fallback_provider(actual_provider)
        if fb_provider:
            log.info(
                "fallback_search",
                query=body.query,
                primary=actual_provider,
                fallback=fb_name,
                primary_results=len(result.results),
            )
            try:
                fb_result = await fb_provider.search(body)
                log.info(
                    "fallback_response",
                    query=body.query,
                    provider=fb_name,
                    result_count=len(fb_result.results),
                    titles=[r.title[:50] for r in fb_result.results[:3]],
                )
                if len(fb_result.results) > len(result.results):
                    result = fb_result
            except Exception as e:
                log.warning("fallback_failed", provider=fb_name, error=str(e))

    # 结果质量不足时跳过缓存
    if len(result.results) >= min_acceptable:
        await set_cached(actual_provider, body.type, body.query, body.lang, body.region, result)
    else:
        log.warning(
            "skip_cache",
            query=body.query,
            provider=result.provider,
            requested=body.count,
            returned=len(result.results),
        )

    return result
