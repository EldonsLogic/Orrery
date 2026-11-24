#!/usr/bin/env python3
"""Engine invisibility crawl test tool (QA-016, ADR-0016).

Crawls same-origin pages, linked JS/CSS bundles, and API paths from a base URL,
checking response bodies, headers (Server, X-*, Set-Cookie) and cookies for
engine markers (Frappe, ERPNext, Desk, RPC routes, engine cookies, etc.).

Exits non-zero on any engine marker hit.
"""
from __future__ import annotations

import argparse
from collections import deque
from dataclasses import asdict, dataclass
import http.client
from http.cookies import SimpleCookie
from html.parser import HTMLParser
import json
import os
from pathlib import Path
import re
import sys
from typing import Any, Callable, Sequence
import urllib.error
import urllib.parse
import urllib.request

DEFAULT_MARKERS_FILE = Path(__file__).resolve().parent / "markers.json"
DEFAULT_USER_AGENT = "Orrery-Invisibility-Crawler/1.0"
CSS_URL_RE = re.compile(r"""url\(\s*['"]?([^'"\)\s]+)['"]?\s*\)""", re.IGNORECASE)
CSS_IMPORT_RE = re.compile(r"""@import\s+['"]([^'"]+)['"]""", re.IGNORECASE)


@dataclass(frozen=True)
class Marker:
    """An engine-identifying marker pattern loaded from configuration."""

    id: str
    pattern: str
    match_type: str  # "substring", "regex", "exact"
    targets: tuple[str, ...]
    case_sensitive: bool
    comment: str

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Marker:
        return cls(
            id=str(data["id"]),
            pattern=str(data["pattern"]),
            match_type=str(data.get("match_type", "substring")),
            targets=tuple(data.get("targets", ["body", "header_value", "cookie_name", "cookie_value"])),
            case_sensitive=bool(data.get("case_sensitive", False)),
            comment=str(data.get("comment", "")),
        )

    def find_in_text(self, text: str) -> list[tuple[int, int, str]]:
        """Find occurrences of marker in text. Returns list of (start, end, matched_text)."""
        if not text:
            return []
        results: list[tuple[int, int, str]] = []
        if self.match_type == "regex":
            flags = 0 if self.case_sensitive else re.IGNORECASE
            try:
                rx = re.compile(self.pattern, flags)
            except re.error:
                return []
            for m in rx.finditer(text):
                results.append((m.start(), m.end(), m.group(0)))
        elif self.match_type == "exact":
            cmp_text = text if self.case_sensitive else text.lower()
            cmp_pattern = self.pattern if self.case_sensitive else self.pattern.lower()
            if cmp_text == cmp_pattern:
                results.append((0, len(text), text))
        else:  # substring
            needle = self.pattern if self.case_sensitive else self.pattern.lower()
            haystack = text if self.case_sensitive else text.lower()
            start = 0
            while True:
                idx = haystack.find(needle, start)
                if idx == -1:
                    break
                end = idx + len(needle)
                results.append((idx, end, text[idx:end]))
                start = idx + max(1, len(needle))
        return results


@dataclass(frozen=True)
class Finding:
    """A detected engine marker occurrence with location and context."""

    url: str
    location: str
    marker_id: str
    marker_pattern: str
    matched_text: str
    reason: str
    snippet: str = ""


class LinkExtractor(HTMLParser):
    """HTML parser extracting links to pages, stylesheets, scripts, and embedded assets."""

    def __init__(self) -> None:
        super().__init__()
        self.links: set[str] = set()

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attr_map = {k.lower(): v for k, v in attrs if v is not None}
        if tag == "a" and "href" in attr_map:
            self.links.add(attr_map["href"])
        elif tag == "link" and "href" in attr_map:
            rel = attr_map.get("rel", "").lower()
            if any(t in rel for t in ("stylesheet", "preload", "modulepreload")) or not rel:
                self.links.add(attr_map["href"])
        elif tag == "script" and "src" in attr_map:
            self.links.add(attr_map["src"])
        elif tag in ("iframe", "frame") and "src" in attr_map:
            self.links.add(attr_map["src"])


class InspectingRedirectHandler(urllib.request.HTTPRedirectHandler):
    """Intercept and inspect redirect responses before following."""

    def __init__(self, on_redirect: Callable[[str, int, http.client.HTTPMessage], None]) -> None:
        super().__init__()
        self._on_redirect = on_redirect

    def redirect_request(
        self,
        req: urllib.request.Request,
        fp: Any,
        code: int,
        msg: str,
        headers: http.client.HTTPMessage,
        newurl: str,
    ) -> urllib.request.Request | None:
        self._on_redirect(req.get_full_url(), code, headers)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def load_markers(path: Path | str) -> list[Marker]:
    """Load markers from JSON catalog."""
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    if isinstance(data, dict) and "markers" in data:
        items = data["markers"]
    elif isinstance(data, list):
        items = data
    else:
        raise ValueError(f"Unrecognized marker catalog format in {path}")
    return [Marker.from_dict(item) for item in items]


def is_same_origin(target_url: str, base_url: str) -> bool:
    """Check if target URL shares the same scheme and netloc with base URL."""
    t_parsed = urllib.parse.urlparse(target_url)
    b_parsed = urllib.parse.urlparse(base_url)
    if not t_parsed.scheme or not t_parsed.netloc:
        return True
    return (
        t_parsed.scheme.lower() == b_parsed.scheme.lower()
        and t_parsed.netloc.lower() == b_parsed.netloc.lower()
    )


def normalize_url(url: str) -> str:
    """Strip URL fragments and collapse consecutive slashes."""
    defrag, _ = urllib.parse.urldefrag(url)
    return defrag


def make_body_snippet(text: str, start_idx: int, end_idx: int) -> tuple[int, int, str]:
    """Return 1-indexed line number, column number, and a single-line context snippet."""
    prefix = text[:start_idx]
    line_num = prefix.count("\n") + 1
    last_nl = prefix.rfind("\n")
    col_num = (start_idx - last_nl) if last_nl != -1 else (start_idx + 1)

    snippet_start = max(0, start_idx - 35)
    snippet_end = min(len(text), end_idx + 35)
    raw = text[snippet_start:snippet_end]
    clean = " ".join(raw.split())
    return line_num, col_num, f"...{clean}..."


class InvisibilityCrawler:
    """Crawl web pages, bundles, and API endpoints, verifying engine invisibility."""

    def __init__(
        self,
        base_url: str,
        markers: Sequence[Marker],
        *,
        api_paths: Sequence[str] | None = None,
        max_pages: int = 50,
        timeout: float = 10.0,
        user_agent: str = DEFAULT_USER_AGENT,
        verbose: bool = False,
    ) -> None:
        self.base_url = normalize_url(base_url.rstrip("/"))
        self.markers = list(markers)
        self.api_paths = list(api_paths or [])
        self.max_pages = max(1, max_pages)
        self.timeout = timeout
        self.user_agent = user_agent
        self.verbose = verbose

        self.visited: set[str] = set()
        self.findings: list[Finding] = []
        self._opener = urllib.request.build_opener(
            InspectingRedirectHandler(self._handle_redirect)
        )

    def _log(self, msg: str) -> None:
        if self.verbose:
            print(f"[crawler] {msg}", file=sys.stderr)

    def _handle_redirect(self, url: str, status_code: int, headers: http.client.HTTPMessage) -> None:
        self._log(f"Redirect {status_code} from {url}")
        self._check_headers(url, headers)
        self._check_cookies(url, headers)

    def _check_headers(self, url: str, headers: http.client.HTTPMessage) -> None:
        for name, value in headers.items():
            # Check header name
            for m in self.markers:
                if any(t in m.targets for t in ("header_name", "all")):
                    matches = m.find_in_text(name)
                    for _, _, matched in matches:
                        self.findings.append(
                            Finding(
                                url=url,
                                location=f"header name '{name}'",
                                marker_id=m.id,
                                marker_pattern=m.pattern,
                                matched_text=matched,
                                reason=m.comment,
                                snippet=f"{name}: {value}",
                            )
                        )
            # Check header value
            for m in self.markers:
                if any(t in m.targets for t in ("header_value", "all")):
                    matches = m.find_in_text(value)
                    for _, _, matched in matches:
                        self.findings.append(
                            Finding(
                                url=url,
                                location=f"header '{name}' value",
                                marker_id=m.id,
                                marker_pattern=m.pattern,
                                matched_text=matched,
                                reason=m.comment,
                                snippet=f"{name}: {value}",
                            )
                        )

    def _check_cookies(self, url: str, headers: http.client.HTTPMessage) -> None:
        set_cookies = headers.get_all("Set-Cookie", [])
        for raw_cookie in set_cookies:
            cookie = SimpleCookie()
            try:
                cookie.load(raw_cookie)
            except Exception:
                continue
            for morsel_key, morsel in cookie.items():
                cookie_val = morsel.value
                # Check cookie name
                for m in self.markers:
                    if any(t in m.targets for t in ("cookie_name", "all")):
                        matches = m.find_in_text(morsel_key)
                        for _, _, matched in matches:
                            self.findings.append(
                                Finding(
                                    url=url,
                                    location=f"cookie name '{morsel_key}'",
                                    marker_id=m.id,
                                    marker_pattern=m.pattern,
                                    matched_text=matched,
                                    reason=m.comment,
                                    snippet=f"Set-Cookie: {raw_cookie}",
                                )
                            )
                # Check cookie value
                for m in self.markers:
                    if any(t in m.targets for t in ("cookie_value", "all")):
                        matches = m.find_in_text(cookie_val)
                        for _, _, matched in matches:
                            self.findings.append(
                                Finding(
                                    url=url,
                                    location=f"cookie '{morsel_key}' value",
                                    marker_id=m.id,
                                    marker_pattern=m.pattern,
                                    matched_text=matched,
                                    reason=m.comment,
                                    snippet=f"{morsel_key}={cookie_val}",
                                )
                            )

    def _check_body(self, url: str, body_text: str) -> None:
        for m in self.markers:
            if any(t in m.targets for t in ("body", "all")):
                matches = m.find_in_text(body_text)
                for start, end, matched in matches:
                    line, col, snippet = make_body_snippet(body_text, start, end)
                    self.findings.append(
                        Finding(
                            url=url,
                            location=f"body line {line}, col {col}",
                            marker_id=m.id,
                            marker_pattern=m.pattern,
                            matched_text=matched,
                            reason=m.comment,
                            snippet=snippet,
                        )
                    )

    def _extract_links(self, current_url: str, content_type: str, text: str) -> set[str]:
        extracted: set[str] = set()
        c_type = content_type.lower()
        if "text/html" in c_type or "application/xhtml" in c_type or not c_type:
            parser = LinkExtractor()
            try:
                parser.feed(text)
                extracted.update(parser.links)
            except Exception:
                pass
        elif "text/css" in c_type:
            for m in CSS_URL_RE.finditer(text):
                extracted.add(m.group(1))
            for m in CSS_IMPORT_RE.finditer(text):
                extracted.add(m.group(1))

        resolved: set[str] = set()
        for link in extracted:
            link = link.strip()
            if not link or link.startswith(("data:", "javascript:", "mailto:", "tel:")):
                continue
            abs_url = normalize_url(urllib.parse.urljoin(current_url, link))
            if is_same_origin(abs_url, self.base_url):
                resolved.add(abs_url)
        return resolved

    def crawl(self) -> list[Finding]:
        """Execute the crawl across base URL, API paths, and linked bundles."""
        queue: deque[str] = deque()
        queue.append(self.base_url)

        for api_path in self.api_paths:
            path_url = normalize_url(urllib.parse.urljoin(self.base_url, api_path))
            if is_same_origin(path_url, self.base_url):
                queue.append(path_url)

        while queue and len(self.visited) < self.max_pages:
            url = queue.popleft()
            if url in self.visited:
                continue
            self.visited.add(url)
            self._log(f"Fetching [{len(self.visited)}/{self.max_pages}] {url}")

            req = urllib.request.Request(
                url,
                headers={
                    "User-Agent": self.user_agent,
                    "Accept": "text/html,application/xhtml+xml,application/json,text/css,application/javascript,*/*",
                },
            )

            status_code: int = 0
            headers: http.client.HTTPMessage | None = None
            body_bytes = b""

            try:
                with self._opener.open(req, timeout=self.timeout) as resp:
                    status_code = resp.status
                    headers = resp.headers
                    body_bytes = resp.read()
            except urllib.error.HTTPError as err:
                status_code = err.code
                headers = err.headers
                body_bytes = err.read()
                self._log(f"HTTPError {status_code} on {url}")
            except (urllib.error.URLError, TimeoutError, OSError) as err:
                self._log(f"Network error on {url}: {err}")
                continue

            if headers is not None:
                self._check_headers(url, headers)
                self._check_cookies(url, headers)

            content_type = headers.get("Content-Type", "") if headers else ""
            try:
                body_text = body_bytes.decode("utf-8", errors="replace")
            except Exception:
                body_text = ""

            self._check_body(url, body_text)

            new_links = self._extract_links(url, content_type, body_text)
            for link in sorted(new_links):
                if link not in self.visited and link not in queue:
                    if len(self.visited) + len(queue) < self.max_pages * 2:
                        queue.append(link)

        return self.findings


def format_report(
    base_url: str,
    visited_urls: list[str],
    findings: list[Finding],
    *,
    as_json: bool = False,
) -> str:
    """Format crawl results for human display or JSON output."""
    if as_json:
        payload = {
            "base_url": base_url,
            "pages_crawled": len(visited_urls),
            "visited_urls": sorted(visited_urls),
            "passed": len(findings) == 0,
            "findings_count": len(findings),
            "findings": [asdict(f) for f in findings],
        }
        return json.dumps(payload, indent=2)

    lines: list[str] = [
        "=" * 70,
        "ENGINE INVISIBILITY CRAWL REPORT (ADR-0016)",
        "=" * 70,
        f"Base URL: {base_url}",
        f"Pages Crawled: {len(visited_urls)}",
        f"Findings Count: {len(findings)}",
        "",
    ]
    if not findings:
        lines.append("RESULT: PASSED (0 engine markers found).")
        lines.append("=" * 70)
        return "\n".join(lines)

    lines.append(f"RESULT: FAILED ({len(findings)} engine markers detected):")
    lines.append("-" * 70)
    for i, f in enumerate(findings, 1):
        lines.append(f"[{i}] URL: {f.url}")
        lines.append(f"    Location: {f.location}")
        lines.append(f"    Marker ID: {f.marker_id} ({f.marker_pattern})")
        lines.append(f"    Matched text: {f.matched_text!r}")
        lines.append(f"    Reason: {f.reason}")
        if f.snippet:
            lines.append(f"    Snippet: {f.snippet}")
        lines.append("")
    lines.append("=" * 70)
    return "\n".join(lines)


def run_crawl(
    base_url: str,
    markers_file: Path | str = DEFAULT_MARKERS_FILE,
    api_paths: Sequence[str] | None = None,
    max_pages: int = 50,
    timeout: float = 10.0,
    verbose: bool = False,
) -> tuple[int, list[str], list[Finding]]:
    """Run an invisibility crawl programmatically. Returns (exit_code, visited, findings)."""
    markers = load_markers(markers_file)
    crawler = InvisibilityCrawler(
        base_url=base_url,
        markers=markers,
        api_paths=api_paths,
        max_pages=max_pages,
        timeout=timeout,
        verbose=verbose,
    )
    findings = crawler.crawl()
    exit_code = 0 if not findings else 1
    return exit_code, sorted(crawler.visited), findings


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Crawl base URL, bundles and API endpoints to verify engine invisibility (ADR-0016)."
    )
    parser.add_argument("--base-url", required=True, help="Base URL to crawl (e.g. http://localhost:8000)")
    parser.add_argument(
        "--api-paths",
        help="Comma-separated API paths to check (e.g. /api/v1/health,/api/v1/auth/session)",
    )
    parser.add_argument(
        "--api-paths-file",
        help="Path to a text file with one API path per line",
    )
    parser.add_argument(
        "--max-pages",
        type=int,
        default=50,
        help="Maximum number of pages/bundles/endpoints to crawl (default: 50)",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=10.0,
        help="HTTP request timeout in seconds (default: 10.0)",
    )
    parser.add_argument(
        "--markers-file",
        type=Path,
        default=DEFAULT_MARKERS_FILE,
        help="Path to markers.json catalog",
    )
    parser.add_argument("--json", action="store_true", help="Output results as JSON")
    parser.add_argument("-v", "--verbose", action="store_true", help="Verbose crawl logging")

    args = parser.parse_args()

    api_paths: list[str] = []
    if args.api_paths:
        api_paths.extend([p.strip() for p in args.api_paths.split(",") if p.strip()])
    if args.api_paths_file:
        with open(args.api_paths_file, "r", encoding="utf-8") as f:
            api_paths.extend([line.strip() for line in f if line.strip() and not line.startswith("#")])

    exit_code, visited, findings = run_crawl(
        base_url=args.base_url,
        markers_file=args.markers_file,
        api_paths=api_paths,
        max_pages=args.max_pages,
        timeout=args.timeout,
        verbose=args.verbose,
    )

    report = format_report(args.base_url, visited, findings, as_json=args.json)
    print(report)
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
