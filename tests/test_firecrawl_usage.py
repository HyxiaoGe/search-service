from unittest.mock import AsyncMock

import httpx

REAL_ASYNC_CLIENT = httpx.AsyncClient


def _usage_client(response_data: dict, calls: list[dict], status_code: int = 200):
    class FakeAsyncClient:
        def __init__(self, timeout: int):
            self.timeout = timeout

        async def __aenter__(self):
            return self

        async def __aexit__(self, _exc_type, _exc, _tb):
            return False

        async def get(self, url: str, headers: dict):
            calls.append({"url": url, "headers": headers, "timeout": self.timeout})
            return httpx.Response(status_code, json=response_data, request=httpx.Request("GET", url))

    return FakeAsyncClient


async def _get_usage():
    from app.main import app

    async with REAL_ASYNC_CLIENT(transport=httpx.ASGITransport(app=app), base_url="http://testserver") as client:
        return await client.get("/usage/firecrawl")


async def test_firecrawl_usage_endpoint_fetches_and_returns_credit_usage(monkeypatch):
    from app.models import ProviderRecordedUsage
    from app.providers import firecrawl, registry

    calls: list[dict] = []
    monkeypatch.setattr(firecrawl.settings, "FIRECRAWL_API_KEY", "fc-test-key")
    monkeypatch.setattr(firecrawl.settings, "FIRECRAWL_API_URL", "https://firecrawl.example/api/")
    monkeypatch.setattr(
        registry,
        "get_recorded_provider_usage",
        AsyncMock(
            return_value=ProviderRecordedUsage(
                provider="firecrawl",
                available=True,
                credits_used=12,
                request_count=3,
                period_start="2025-01-01T00:00:00Z",
                period_end="2025-01-31T23:59:59Z",
            )
        ),
        raising=False,
    )
    monkeypatch.setattr(
        firecrawl.httpx,
        "AsyncClient",
        _usage_client(
            {
                "success": True,
                "data": {
                    "remainingCredits": 250,
                    "planCredits": 1000,
                    "billingPeriodStart": "2025-01-01T00:00:00Z",
                    "billingPeriodEnd": "2025-01-31T23:59:59Z",
                },
            },
            calls,
        ),
    )

    response = await _get_usage()

    assert response.status_code == 200
    assert response.json() == {
        "provider": "firecrawl",
        "available": True,
        "remaining_credits": 250,
        "plan_credits": 1000,
        "used_credits": 750,
        "usage_ratio": 0.75,
        "billing_period_start": "2025-01-01T00:00:00Z",
        "billing_period_end": "2025-01-31T23:59:59Z",
        "recorded_usage": {
            "provider": "firecrawl",
            "available": True,
            "credits_used": 12,
            "request_count": 3,
            "period_start": "2025-01-01T00:00:00Z",
            "period_end": "2025-01-31T23:59:59Z",
            "source": "search_response_credits_used",
        },
    }
    assert calls == [
        {
            "url": "https://firecrawl.example/api/v2/team/credit-usage",
            "headers": {"Authorization": "Bearer fc-test-key"},
            "timeout": 20,
        }
    ]


async def test_firecrawl_usage_endpoint_does_not_call_firecrawl_without_api_key(monkeypatch):
    from app.providers import firecrawl

    class ExplodingAsyncClient:
        def __init__(self, *_args, **_kwargs):
            raise AssertionError("缺少 Firecrawl API key 时不应创建 HTTP 客户端")

    monkeypatch.setattr(firecrawl.settings, "FIRECRAWL_API_KEY", "")
    monkeypatch.setattr(firecrawl.httpx, "AsyncClient", ExplodingAsyncClient)

    response = await _get_usage()

    assert response.status_code == 200
    assert response.json() == {
        "provider": "firecrawl",
        "available": False,
        "remaining_credits": None,
        "plan_credits": None,
        "used_credits": None,
        "usage_ratio": None,
        "billing_period_start": None,
        "billing_period_end": None,
        "recorded_usage": None,
    }


async def test_firecrawl_usage_endpoint_leaves_used_and_ratio_null_when_remaining_exceeds_plan(monkeypatch):
    from app.providers import firecrawl

    calls: list[dict] = []
    monkeypatch.setattr(firecrawl.settings, "FIRECRAWL_API_KEY", "fc-test-key")
    monkeypatch.setattr(firecrawl.settings, "FIRECRAWL_API_URL", "https://api.firecrawl.dev")
    monkeypatch.setattr(
        firecrawl.httpx,
        "AsyncClient",
        _usage_client(
            {
                "success": True,
                "data": {
                    "remainingCredits": 1200,
                    "planCredits": 1000,
                    "billingPeriodStart": "2025-01-01T00:00:00Z",
                    "billingPeriodEnd": "2025-01-31T23:59:59Z",
                },
            },
            calls,
        ),
    )

    response = await _get_usage()

    assert response.status_code == 200
    body = response.json()
    assert body["remaining_credits"] == 1200
    assert body["plan_credits"] == 1000
    assert body["used_credits"] is None
    assert body["usage_ratio"] is None


async def test_firecrawl_usage_endpoint_maps_firecrawl_failures_to_502_without_leaking_key(monkeypatch):
    from app.providers import firecrawl

    calls: list[dict] = []
    monkeypatch.setattr(firecrawl.settings, "FIRECRAWL_API_KEY", "fc-secret-key")
    monkeypatch.setattr(firecrawl.settings, "FIRECRAWL_API_URL", "https://api.firecrawl.dev")
    monkeypatch.setattr(
        firecrawl.httpx,
        "AsyncClient",
        _usage_client({"success": False, "error": "unauthorized fc-secret-key"}, calls, status_code=500),
    )

    response = await _get_usage()

    assert response.status_code == 502
    assert response.json() == {"detail": "Firecrawl usage request failed"}
    assert "fc-secret-key" not in response.text


async def test_firecrawl_historical_usage_endpoint_fetches_periods_and_masks_api_key(monkeypatch):
    from app.providers import firecrawl

    calls: list[dict] = []

    class FakeAsyncClient:
        def __init__(self, timeout: int):
            self.timeout = timeout

        async def __aenter__(self):
            return self

        async def __aexit__(self, _exc_type, _exc, _tb):
            return False

        async def get(self, url: str, headers: dict, params: dict | None = None):
            calls.append({"url": url, "headers": headers, "params": params, "timeout": self.timeout})
            return httpx.Response(
                200,
                json={
                    "success": True,
                    "periods": [
                        {
                            "startDate": "2026-06-01T00:00:00Z",
                            "endDate": "2026-06-30T23:59:59Z",
                            "apiKey": "fc-1234567890abcdef",
                            "totalCredits": 42,
                        }
                    ],
                },
                request=httpx.Request("GET", url),
            )

    monkeypatch.setattr(firecrawl.settings, "FIRECRAWL_API_KEY", "fc-test-key")
    monkeypatch.setattr(firecrawl.settings, "FIRECRAWL_API_URL", "https://api.firecrawl.dev")
    monkeypatch.setattr(firecrawl.httpx, "AsyncClient", FakeAsyncClient)

    from app.main import app

    async with REAL_ASYNC_CLIENT(transport=httpx.ASGITransport(app=app), base_url="http://testserver") as client:
        response = await client.get("/usage/firecrawl/historical?by_api_key=true")

    assert response.status_code == 200
    assert response.json() == {
        "provider": "firecrawl",
        "available": True,
        "by_api_key": True,
        "periods": [
            {
                "start_date": "2026-06-01T00:00:00Z",
                "end_date": "2026-06-30T23:59:59Z",
                "api_key": "fc-123...cdef",
                "total_credits": 42,
            }
        ],
    }
    assert calls == [
        {
            "url": "https://api.firecrawl.dev/v2/team/credit-usage/historical",
            "headers": {"Authorization": "Bearer fc-test-key"},
            "params": {"byApiKey": "true"},
            "timeout": 20,
        }
    ]
    assert "fc-1234567890abcdef" not in response.text


async def test_firecrawl_historical_usage_accepts_current_firecrawl_credits_used_shape(monkeypatch):
    from app.providers import firecrawl

    class FakeAsyncClient:
        def __init__(self, timeout: int):
            self.timeout = timeout

        async def __aenter__(self):
            return self

        async def __aexit__(self, _exc_type, _exc, _tb):
            return False

        async def get(self, url: str, headers: dict, params: dict | None = None):
            return httpx.Response(
                200,
                json={
                    "success": True,
                    "periods": [
                        {
                            "startDate": "2026-06-01T00:00:00.000Z",
                            "endDate": None,
                            "creditsUsed": 32,
                        }
                    ],
                },
                request=httpx.Request("GET", url),
            )

    monkeypatch.setattr(firecrawl.settings, "FIRECRAWL_API_KEY", "fc-test-key")
    monkeypatch.setattr(firecrawl.settings, "FIRECRAWL_API_URL", "https://api.firecrawl.dev")
    monkeypatch.setattr(firecrawl.httpx, "AsyncClient", FakeAsyncClient)

    from app.main import app

    async with REAL_ASYNC_CLIENT(transport=httpx.ASGITransport(app=app), base_url="http://testserver") as client:
        response = await client.get("/usage/firecrawl/historical")

    assert response.status_code == 200
    assert response.json() == {
        "provider": "firecrawl",
        "available": True,
        "by_api_key": False,
        "periods": [
            {
                "start_date": "2026-06-01T00:00:00.000Z",
                "end_date": "",
                "api_key": None,
                "total_credits": 32,
            }
        ],
    }
