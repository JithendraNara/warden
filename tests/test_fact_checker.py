import httpx

from warden.runtime.fact_checker import FactChecker, FactReport


class _FakeClient:
    def __init__(self, responses: dict[str, tuple[int, object]]) -> None:
        self._responses = responses
        self.calls: list[tuple[str, str]] = []

    def get(self, url: str, params: dict | None = None):  # type: ignore[override]
        key = url + (("?" + "&".join(f"{k}={v}" for k, v in params.items())) if params else "")
        self.calls.append(("GET", key))
        status, payload = self._responses.get(key, self._responses.get(url, (404, {})))
        return _FakeResponse(status, payload)

    def head(self, url: str):
        self.calls.append(("HEAD", url))
        status, _ = self._responses.get(url, (404, {}))
        return _FakeResponse(status, {})

    def close(self) -> None:
        return None


class _FakeResponse:
    def __init__(self, status: int, payload: object) -> None:
        self.status_code = status
        self._payload = payload
        self.text = ""

    def json(self) -> object:
        return self._payload


def _make_checker(responses: dict[str, tuple[int, object]]) -> FactChecker:
    client = _FakeClient(responses)
    checker = FactChecker(client=client)  # type: ignore[arg-type]
    return checker


def test_pypi_known_package_version_passes() -> None:
    checker = _make_checker(
        {
            "https://pypi.org/pypi/numpy/json": (
                200,
                {"releases": {"1.24.0": [], "1.25.0": []}},
            )
        }
    )
    report = checker.check_text("upgrade numpy 1.24.0 fixes this")
    assert report.ok, report.to_dict()
    assert any(c.kind == "pypi" and c.verdict == "ok" for c in report.checks)


def test_pypi_unknown_package_fails() -> None:
    checker = _make_checker(
        {
            "https://pypi.org/pypi/notarealpkg/json": (404, {}),
        }
    )
    report = checker.check_text("upgrade notarealpkg 1.0 to fix this")
    assert not report.ok
    assert any(c.identifier == "notarealpkg" and c.verdict == "not_found" for c in report.checks)


def test_cve_known_id_passes() -> None:
    checker = _make_checker(
        {
            "https://services.nvd.nist.gov/rest/json/cves/2.0?cveId=CVE-2021-44228": (
                200,
                {"totalResults": 1},
            ),
        }
    )
    report = checker.check_text("This is CVE-2021-44228 (Log4Shell)")
    assert report.ok
    assert any(c.kind == "cve" and c.verdict == "ok" for c in report.checks)


def test_cve_fabricated_id_fails() -> None:
    checker = _make_checker(
        {
            "https://services.nvd.nist.gov/rest/json/cves/2.0?cveId=CVE-2099-99999": (
                200,
                {"totalResults": 0},
            ),
        }
    )
    report = checker.check_text("This is CVE-2099-99999, a made-up advisory.")
    assert not report.ok


def test_url_404_fails() -> None:
    checker = _make_checker(
        {
            "https://example.invalid/not-real": (404, {}),
        }
    )
    report = checker.check_text("See https://example.invalid/not-real for details")
    assert not report.ok


def test_url_200_passes() -> None:
    checker = _make_checker(
        {
            "https://example.com/ok": (200, {}),
        }
    )
    report = checker.check_text("See https://example.com/ok")
    assert report.ok


def test_empty_text_returns_ok() -> None:
    checker = FactChecker(client=_FakeClient({}))  # type: ignore[arg-type]
    report = checker.check_text("a simple statement with no external claims")
    assert isinstance(report, FactReport)
    assert report.ok
    assert report.checks == []
