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
