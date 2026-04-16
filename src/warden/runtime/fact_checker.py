"""Real-world fact checker for warden agent outputs.

This module complements :mod:`hallucination_audit`. Where the audit
checks that the agent's output stays grounded in the **source issue**,
the fact checker checks that claims about the **outside world** —
package names, versions, CVEs, URLs — are actually real.

Design constraints:

- No extra heavy dependencies: we reuse ``httpx`` which warden already
  imports for the GitHub adapter.
- Registry lookups hit public, unauthenticated endpoints only.
- Every check has a short timeout; on failure the verdict is
  ``unverifiable`` rather than silently "ok".
- The module returns structured data so the caller (CLI, example
  scripts, CI) can decide how to present it.

Supported verifications today:

- **PyPI packages**: ``https://pypi.org/pypi/{name}/json`` and
  optional version existence.
- **npm packages**: ``https://registry.npmjs.org/{name}`` and optional
  version existence.
- **CVE identifiers**: NVD REST API v2 existence check.
- **URLs**: HTTP HEAD check (with a GET fallback on 405).

The intent is to catch obvious fabrications, not build a full
knowledge-base. If a claim cannot be verified with these sources we
say so explicitly instead of pretending it's true.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Iterable, Literal

import httpx

logger = logging.getLogger("warden.fact_checker")


CheckVerdict = Literal["ok", "not_found", "unverifiable"]


_PYPI_RE = re.compile(
    r"(?i)\b(?:pypi|pip|python package)[\s:]+([A-Za-z0-9_\-]+)(?:[=\s]*([0-9][0-9A-Za-z.\-+]*))?"
)
_GENERIC_PYVERSION_RE = re.compile(
    r"\b([a-z][a-z0-9_\-]{1,40})(?:==| v|@|\s)([0-9]+\.[0-9]+(?:\.[0-9]+)?)\b"
)
_NPM_RE = re.compile(
    r"(?i)\b(?:npm|yarn|pnpm)[\s:]+([@]?[A-Za-z0-9_\-/]+)(?:[@\s]+([0-9][0-9A-Za-z.\-+]*))?"
)
_NPM_SCOPED_RE = re.compile(r"\b(@[a-z0-9][a-z0-9_\-]*\/[a-z0-9][a-z0-9_\-]*)(?:@([0-9][0-9A-Za-z.\-+]*))?")
_CVE_RE = re.compile(r"\bCVE-(\d{4})-(\d{4,7})\b")
_URL_RE = re.compile(r"https?://[^\s)>]+")


# Package names we never verify (too generic / language keywords / etc.)
_IGNORED_PACKAGE_NAMES = frozenset(
    {
        "api",
        "app",
        "node",
        "python",
        "ruby",
        "go",
        "http",
        "https",
        "json",
        "yaml",
        "xml",
        "file",
        "data",
        "none",
        "null",
        "true",
        "false",
        "type",
    }
)


@dataclass(slots=True)
class FactCheck:
    kind: str  # "pypi", "npm", "cve", "url"
    identifier: str
    version: str | None
    verdict: CheckVerdict
    detail: str


@dataclass(slots=True)
class FactReport:
    ok: bool
    checks: list[FactCheck] = field(default_factory=list)

    def to_dict(self) -> dict[str, object]:
        return {
            "ok": self.ok,
            "checks": [
                {
                    "kind": check.kind,
                    "identifier": check.identifier,
                    "version": check.version,
                    "verdict": check.verdict,
                    "detail": check.detail,
                }
                for check in self.checks
            ],
        }


class FactChecker:
    """Performs real-world grounding checks against public registries."""

    def __init__(self, client: httpx.Client | None = None, *, timeout: float = 5.0) -> None:
        self._client = client or httpx.Client(timeout=timeout, follow_redirects=True)
        self._owned_client = client is None

    def close(self) -> None:
        if self._owned_client:
            self._client.close()

    # ------------------------------------------------------------------ #
    # Extraction                                                         #
    # ------------------------------------------------------------------ #

    def extract_claims(self, text: str) -> list[FactCheck]:
        """Pre-emit a list of ``FactCheck`` stubs with ``unverifiable`` verdict.

        The caller can either call :meth:`check_text` for the full
        verify loop or use this method to see what would be checked.
        """

        claims: list[FactCheck] = []
        for name, version in _extract_pypi_claims(text):
            claims.append(
                FactCheck(
                    kind="pypi",
                    identifier=name,
                    version=version,
                    verdict="unverifiable",
                    detail="not yet checked",
                )
            )
        for name, version in _extract_npm_claims(text):
            claims.append(
                FactCheck(
                    kind="npm",
                    identifier=name,
                    version=version,
                    verdict="unverifiable",
                    detail="not yet checked",
                )
            )
        for cve_id in _extract_cves(text):
            claims.append(
                FactCheck(
                    kind="cve",
                    identifier=cve_id,
                    version=None,
                    verdict="unverifiable",
                    detail="not yet checked",
                )
            )
        for url in _extract_urls(text):
            claims.append(
                FactCheck(
                    kind="url",
                    identifier=url,
                    version=None,
                    verdict="unverifiable",
                    detail="not yet checked",
                )
            )
        return claims

    # ------------------------------------------------------------------ #
    # Verification                                                       #
    # ------------------------------------------------------------------ #

    def check_text(self, text: str) -> FactReport:
        claims = self.extract_claims(text)
        report = FactReport(ok=True, checks=[])
        for claim in claims:
            if claim.kind == "pypi":
                check = self._check_pypi(claim.identifier, claim.version)
            elif claim.kind == "npm":
                check = self._check_npm(claim.identifier, claim.version)
            elif claim.kind == "cve":
                check = self._check_cve(claim.identifier)
            elif claim.kind == "url":
                check = self._check_url(claim.identifier)
            else:  # pragma: no cover - defensive
                continue
            report.checks.append(check)
            if check.verdict == "not_found":
                report.ok = False
        return report

    # ------------------------------------------------------------------ #
    # Individual checks                                                  #
    # ------------------------------------------------------------------ #

    def _check_pypi(self, name: str, version: str | None) -> FactCheck:
        url = f"https://pypi.org/pypi/{name}/json"
        try:
            response = self._client.get(url)
        except httpx.HTTPError as exc:
            return FactCheck("pypi", name, version, "unverifiable", f"network error: {exc}")
        if response.status_code == 404:
            return FactCheck("pypi", name, version, "not_found", "package not found on PyPI")
        if response.status_code != 200:
            return FactCheck(
                "pypi", name, version, "unverifiable",
                f"unexpected status {response.status_code}",
            )
        payload = _safe_json(response)
        if version is None:
            return FactCheck("pypi", name, version, "ok", "package exists on PyPI")
        releases = (payload.get("releases") or {}) if isinstance(payload, dict) else {}
        if version in releases:
            return FactCheck("pypi", name, version, "ok", "version exists on PyPI")
        return FactCheck(
            "pypi", name, version, "not_found",
            f"version {version} not in PyPI releases",
        )

    def _check_npm(self, name: str, version: str | None) -> FactCheck:
        url = f"https://registry.npmjs.org/{name}"
        try:
            response = self._client.get(url)
        except httpx.HTTPError as exc:
            return FactCheck("npm", name, version, "unverifiable", f"network error: {exc}")
        if response.status_code == 404:
            return FactCheck("npm", name, version, "not_found", "package not found on npm")
        if response.status_code != 200:
            return FactCheck(
                "npm", name, version, "unverifiable",
                f"unexpected status {response.status_code}",
            )
        payload = _safe_json(response)
        if version is None:
            return FactCheck("npm", name, version, "ok", "package exists on npm")
        versions = (payload.get("versions") or {}) if isinstance(payload, dict) else {}
        if version in versions:
            return FactCheck("npm", name, version, "ok", "version exists on npm")
        return FactCheck(
            "npm", name, version, "not_found",
            f"version {version} not in npm registry",
        )

    def _check_cve(self, cve_id: str) -> FactCheck:
        url = "https://services.nvd.nist.gov/rest/json/cves/2.0"
        try:
            response = self._client.get(url, params={"cveId": cve_id})
        except httpx.HTTPError as exc:
            return FactCheck("cve", cve_id, None, "unverifiable", f"network error: {exc}")
        if response.status_code != 200:
            return FactCheck(
                "cve", cve_id, None, "unverifiable",
                f"NVD status {response.status_code}",
            )
        payload = _safe_json(response)
        total = 0
        if isinstance(payload, dict):
            total = int(payload.get("totalResults") or 0)
        if total >= 1:
            return FactCheck("cve", cve_id, None, "ok", "CVE found in NVD")
        return FactCheck("cve", cve_id, None, "not_found", "CVE not present in NVD")

    def _check_url(self, url: str) -> FactCheck:
        cleaned = url.rstrip(".,);")
        try:
            response = self._client.head(cleaned)
            if response.status_code == 405:
                response = self._client.get(cleaned)
        except httpx.HTTPError as exc:
            return FactCheck("url", cleaned, None, "unverifiable", f"network error: {exc}")
        if 200 <= response.status_code < 400:
            return FactCheck("url", cleaned, None, "ok", f"resolvable ({response.status_code})")
        if response.status_code == 404:
            return FactCheck("url", cleaned, None, "not_found", "HTTP 404")
        return FactCheck(
            "url", cleaned, None, "unverifiable",
            f"HTTP {response.status_code}",
        )


# --------------------------------------------------------------------- #
# Extraction helpers                                                    #
# --------------------------------------------------------------------- #


def _extract_pypi_claims(text: str) -> Iterable[tuple[str, str | None]]:
    seen: set[tuple[str, str | None]] = set()
    for match in _PYPI_RE.finditer(text):
        name = match.group(1).lower()
        if name in _IGNORED_PACKAGE_NAMES:
            continue
        version = _normalize_version(match.group(2))
        key = (name, version)
        if key not in seen:
            seen.add(key)
            yield key
    for match in _GENERIC_PYVERSION_RE.finditer(text):
        name = match.group(1).lower()
        if name in _IGNORED_PACKAGE_NAMES:
            continue
        version = _normalize_version(match.group(2))
        key = (name, version)
        if key not in seen:
            seen.add(key)
            yield key


def _normalize_version(raw: str | None) -> str | None:
    if raw is None:
        return None
    return raw.rstrip(".,;:)!?")


def _extract_npm_claims(text: str) -> Iterable[tuple[str, str | None]]:
    seen: set[tuple[str, str | None]] = set()
    for match in _NPM_RE.finditer(text):
        name = match.group(1)
        version = match.group(2)
        key = (name, version)
        if key not in seen:
            seen.add(key)
            yield key
    for match in _NPM_SCOPED_RE.finditer(text):
        name = match.group(1)
        version = match.group(2)
        key = (name, version)
        if key not in seen:
            seen.add(key)
            yield key


def _extract_cves(text: str) -> Iterable[str]:
    seen: set[str] = set()
    for match in _CVE_RE.finditer(text):
        year, nnn = match.group(1), match.group(2)
        cve_id = f"CVE-{year}-{nnn}"
        if cve_id not in seen:
            seen.add(cve_id)
            yield cve_id


def _extract_urls(text: str) -> Iterable[str]:
    seen: set[str] = set()
    for match in _URL_RE.finditer(text):
        url = match.group(0).rstrip(".,);")
        if url not in seen:
            seen.add(url)
            yield url


def _safe_json(response: httpx.Response) -> object:
    try:
        return response.json()
    except ValueError:
        return {}
