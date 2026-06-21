from app.models import SearchRequest, SearchResponse, SearchResultItem, SearchType


def test_search_request_defaults():
    req = SearchRequest(query="test")
    assert req.type == SearchType.WEB
    assert req.count == 10
    assert req.page == 1
    assert req.lang == "en"


def test_search_response_serialization():
    resp = SearchResponse(
        query="test",
        type=SearchType.WEB,
        provider="brave",
        cached=False,
        results=[
            SearchResultItem(
                title="Test",
                url="https://example.com",
                description="A test result",
            )
        ],
    )
    data = resp.model_dump()
    assert data["query"] == "test"
    assert len(data["results"]) == 1
    assert data["results"][0]["published_at"] is None


def test_cache_key_changes_when_result_shaping_params_change():
    from app.cache import build_cache_key

    base = SearchRequest(query="fusion", count=5, freshness="pw", page=1)
    monthly = SearchRequest(query="fusion", count=5, freshness="pm", page=1)
    more = SearchRequest(query="fusion", count=10, freshness="pw", page=1)
    second_page = SearchRequest(query="fusion", count=5, freshness="pw", page=2)
    filtered = SearchRequest(query="fusion", count=5, freshness="pw", page=1, domain_filters=["example.com"])

    assert build_cache_key("brave", base) != build_cache_key("brave", monthly)
    assert build_cache_key("brave", base) != build_cache_key("brave", more)
    assert build_cache_key("brave", base) != build_cache_key("brave", second_page)
    assert build_cache_key("brave", base) != build_cache_key("brave", filtered)


async def test_search_route_marks_fallback_provider_provenance(monkeypatch):
    from starlette.requests import Request

    from app.routes import search as search_route

    class Provider:
        def __init__(self, response: SearchResponse):
            self.response = response

        async def search(self, request: SearchRequest) -> SearchResponse:
            return self.response

    primary_response = SearchResponse(
        query="fusion",
        type=SearchType.WEB,
        provider="brave",
        results=[
            SearchResultItem(title="one", url="https://one.example", description="one"),
        ],
    )
    fallback_response = SearchResponse(
        query="fusion",
        type=SearchType.WEB,
        provider="tavily",
        results=[
            SearchResultItem(title="one", url="https://one.example", description="one"),
            SearchResultItem(title="two", url="https://two.example", description="two"),
            SearchResultItem(title="three", url="https://three.example", description="three"),
        ],
    )

    async def fake_get_cached(*_args, **_kwargs):
        return None

    cached_calls = []

    async def fake_set_cached(*args):
        cached_calls.append(args)

    monkeypatch.setattr(search_route, "get_cached", fake_get_cached)
    monkeypatch.setattr(search_route, "set_cached", fake_set_cached)
    monkeypatch.setattr(search_route, "get_provider", lambda _name=None: Provider(primary_response))
    monkeypatch.setattr(
        search_route,
        "get_fallback_provider",
        lambda _primary: ("tavily", Provider(fallback_response)),
    )

    request = Request(
        {
            "type": "http",
            "method": "POST",
            "path": "/search",
            "headers": [],
            "query_string": b"",
            "client": ("127.0.0.1", 12345),
            "server": ("testserver", 80),
            "scheme": "http",
        }
    )
    body = SearchRequest(query="fusion", provider="brave", count=4)

    response = await search_route.search.__wrapped__(request, body)

    assert response.provider == "tavily"
    assert response.requested_provider == "brave"
    assert response.result_provider == "tavily"
    assert response.fallback_used is True
    assert response.provider_chain == ["brave", "tavily"]
    assert cached_calls[0][0] == "tavily"
