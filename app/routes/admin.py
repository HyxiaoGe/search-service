from fastapi import APIRouter

from app.cache import flush_cache
from app.providers.registry import list_providers

router = APIRouter()


@router.get("/health")
async def health() -> dict:
    return {"status": "ok"}


@router.get("/providers")
async def providers() -> list[dict]:
    return list_providers()


@router.delete("/cache")
async def clear_cache() -> dict:
    count = await flush_cache()
    return {"flushed": count}
