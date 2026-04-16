from warden.adapters.github import GitHubAdapter


class _FakeResponse:
    def __init__(self, payload: object, headers: dict[str, str] | None = None) -> None:
        self._payload = payload
        self.headers = headers or {"x-ratelimit-remaining": "4999", "x-ratelimit-reset": "0"}
        self.status_code = 200

    def raise_for_status(self) -> None:
        return None

    def json(self) -> object:
        return self._payload


class _FakeClient:
    def __init__(self, responses: dict[str, object]) -> None:
        self._responses = responses
        self.calls: list[tuple[str, str, dict[str, object] | None]] = []

    def get(self, url: str, headers: dict[str, str], params: dict[str, object] | None = None):
        self.calls.append(("GET", url, params))
        return _FakeResponse(self._responses[url])

    def post(self, url: str, headers: dict[str, str], json: dict[str, object]):
        self.calls.append(("POST", url, json))
        return _FakeResponse(self._responses[url])

    def close(self) -> None:  # pragma: no cover
        return None


def test_fetch_issue_returns_typed_record() -> None:
    client = _FakeClient(
        {
            "https://api.github.com/repos/example/demo/issues/1": {
                "number": 1,
                "title": "A bug",
                "body": "Something broke.",
                "state": "open",
                "labels": [{"name": "bug"}, "needs-triage"],
                "comments": 2,
                "user": {"login": "author"},
                "html_url": "https://github.com/example/demo/issues/1",
            }
        }
    )
    adapter = GitHubAdapter(token="test", client=client)  # type: ignore[arg-type]
    issue = adapter.fetch_issue("example/demo", 1)
    assert issue.number == 1
    assert issue.labels == ("bug", "needs-triage")
    assert issue.author == "author"


def test_search_similar_issues_builds_query() -> None:
    client = _FakeClient(
        {
            "https://api.github.com/search/issues": {
                "items": [
                    {
                        "number": 11,
                        "title": "similar bug",
                        "body": "",
                        "state": "closed",
                        "labels": ["bug"],
                        "comments": 0,
                        "user": {"login": "someone"},
                        "html_url": "https://github.com/example/demo/issues/11",
                    }
                ]
            }
        }
    )
    adapter = GitHubAdapter(token=None, client=client)  # type: ignore[arg-type]
    issues = adapter.search_similar_issues("example/demo", "crash startup", limit=3)
    assert len(issues) == 1
    assert issues[0].number == 11
    method, url, params = client.calls[0]
    assert method == "GET"
    assert url.endswith("/search/issues")
    assert params == {"q": "repo:example/demo is:issue crash startup", "per_page": 3, "sort": "updated"}
