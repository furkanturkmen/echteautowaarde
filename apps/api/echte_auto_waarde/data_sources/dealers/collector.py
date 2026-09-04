"""Shared plumbing for the public dealer-page pilot.

This is a deliberately small pilot, not a harvesting system. It reads a handful
of listings from two dealers' own public inventory pages so the valuation
methodology can be exercised against real asking prices at all.

**What it will not do.** It does not log in, solve a challenge, rotate an
identity or a proxy, disguise its user agent, use hidden or app endpoints, or
run requests in parallel. It sends one request at a time with a delay, and if a
site disallows it in robots.txt, blocks it, or answers with a challenge, the run
stops for that source. There is no bypass path in this module, by design.

**What it stores.** Facts a valuation needs: make, model, variant, year,
mileage, asking price, fuel, transmission, the canonical URL and a stable
reference. Not photographs, not descriptions, not marketing copy, and not the
telephone numbers and email addresses these pages also contain.

**What it does not promise.** robots.txt permitting a request is not the same as
a licence to reuse the data. A collection of listings can attract database
rights, dealers may object, and terms can change. Recurring or larger collection
belongs in a permission, feed or API arrangement — not here.
"""

from __future__ import annotations

import html as html_entities
import logging
import re
import time
import urllib.robotparser
from dataclasses import dataclass, field
from datetime import UTC, datetime
from urllib.parse import urljoin, urlparse

import httpx

from echte_auto_waarde.config import get_settings

logger = logging.getLogger(__name__)

# The cap is the point of the pilot. `MAX` is not configurable away.
DEFAULT_LISTING_LIMIT = 20
MAX_LISTING_LIMIT = 25

# Signs that a site does not want an automated client. Any of them stops the
# run for that source; none of them is worked around.
CHALLENGE_MARKERS = (
    "captcha",
    "cf-challenge",
    "just a moment",
    "attention required",
    "access denied",
    "verify you are human",
)
BLOCKED_STATUS_CODES = frozenset({401, 402, 403, 405, 406, 429, 451})


class DealerCollectionError(RuntimeError):
    """Collection cannot continue for this source, and will not be forced."""


class RobotsDisallowed(DealerCollectionError):
    """robots.txt disallows the path we would read."""


class CollectionBlocked(DealerCollectionError):
    """The site blocked us or presented a challenge. We stop here."""


@dataclass
class RobotsDecision:
    allowed: bool
    detail: str
    robots_found: bool


@dataclass
class PoliteFetcher:
    """One request at a time, with a delay, and no retries.

    The robots file is fetched once per run and reused; a run that reads two
    pages of the same site asks the same question once.
    """

    user_agent: str
    delay_seconds: float
    timeout_seconds: float
    requests_made: int = 0
    _robots: dict[str, urllib.robotparser.RobotFileParser] = field(default_factory=dict)
    _last_request_at: float | None = None

    def check_robots(self, url: str) -> RobotsDecision:
        """Evaluate `url` against the site's robots.txt, failing closed.

        A missing robots.txt is reported as "no prohibition found" and never as
        permission — it means nobody said no, which is a different thing.
        """
        parsed = urlparse(url)
        origin = f"{parsed.scheme}://{parsed.netloc}"
        robots_url = urljoin(origin, "/robots.txt")

        parser = self._robots.get(origin)
        if parser is None:
            parser = urllib.robotparser.RobotFileParser()
            try:
                response = self._request(robots_url)
            except DealerCollectionError:
                raise
            except httpx.HTTPError as error:
                raise DealerCollectionError(f"robots.txt unreachable: {error}") from error

            if response.status_code == httpx.codes.NOT_FOUND:
                parser.parse([])
                self._robots[origin] = parser
                return RobotsDecision(
                    allowed=True,
                    detail="no robots.txt published (no prohibition found; not permission)",
                    robots_found=False,
                )
            if response.status_code != httpx.codes.OK:
                raise DealerCollectionError(
                    f"robots.txt returned HTTP {response.status_code}; stopping"
                )
            parser.parse(response.text.splitlines())
            self._robots[origin] = parser

        allowed = parser.can_fetch(self.user_agent, url)
        return RobotsDecision(
            allowed=allowed,
            detail=("robots.txt allows this path" if allowed else "robots.txt disallows this path"),
            robots_found=True,
        )

    def get(self, url: str) -> str:
        """Fetch one page, after robots agreed and the delay has passed."""
        decision = self.check_robots(url)
        if not decision.allowed:
            raise RobotsDisallowed(f"{url}: {decision.detail}")

        response = self._request(url)
        if response.status_code in BLOCKED_STATUS_CODES:
            raise CollectionBlocked(
                f"{url} answered HTTP {response.status_code}; stopping this source"
            )
        if response.status_code != httpx.codes.OK:
            raise DealerCollectionError(f"{url} answered HTTP {response.status_code}")

        body = response.text
        lowered = body[:4000].lower()
        if any(marker in lowered for marker in CHALLENGE_MARKERS):
            raise CollectionBlocked(f"{url} presented a challenge page; stopping this source")
        return body

    def _request(self, url: str) -> httpx.Response:
        self._wait()
        self.requests_made += 1
        logger.info("GET %s", url)
        return httpx.get(
            url,
            headers={"User-Agent": self.user_agent, "Accept": "text/html,application/xhtml+xml"},
            timeout=self.timeout_seconds,
            follow_redirects=True,
        )

    def _wait(self) -> None:
        if self._last_request_at is None:
            self._last_request_at = time.monotonic()
            return
        elapsed = time.monotonic() - self._last_request_at
        remaining = self.delay_seconds - elapsed
        if remaining > 0:
            time.sleep(remaining)
        self._last_request_at = time.monotonic()


def build_fetcher() -> PoliteFetcher:
    settings = get_settings()
    return PoliteFetcher(
        user_agent=settings.dealer_user_agent,
        delay_seconds=max(settings.dealer_request_delay_seconds, 1.0),
        timeout_seconds=settings.dealer_timeout_seconds,
    )


def clamp_limit(limit: int | None) -> int:
    """Never more than the pilot's hard maximum, whatever was asked for."""
    if limit is None:
        return DEFAULT_LISTING_LIMIT
    return max(1, min(int(limit), MAX_LISTING_LIMIT))


# -- Text helpers -------------------------------------------------------------

_TAG_RE = re.compile(r"<[^>]+>")
_WHITESPACE_RE = re.compile(r"\s+")
_COMMENT_RE = re.compile(r"<!--.*?-->", re.S)

# Subtitles on these pages mix the variant with sales copy. We keep the
# technical part and drop the offer: "6 maanden garantie" is not a trim level.
_MARKETING_PHRASES = re.compile(
    r"\b("
    r"garantie|inruil|actie|aanbieding|nieuwstaat|dealeronderhouden|"
    r"rijklaar|incl\.?\s*btw|excl\.?\s*btw|btw[- ]?vrij|marge|financiering|"
    r"private\s*lease|nu\s*voor|op\s*voorraad|direct\s*leverbaar"
    r")\b",
    re.IGNORECASE,
)


def unescape(fragment: str) -> str:
    """HTML entities as characters. Pages write `&euro;` and `&nbsp;` freely."""
    return html_entities.unescape(fragment)


def text_of(fragment: str) -> str:
    """Visible text of an HTML fragment, collapsed."""
    without_comments = _COMMENT_RE.sub(" ", fragment)
    return _WHITESPACE_RE.sub(" ", unescape(_TAG_RE.sub(" ", without_comments))).strip()


# Sales copy is usually appended to the specification, often without a
# separator ("... quattro ABTMTM Tuning 6 maanden garantie"), so the subtitle is
# cut at the offer rather than discarded whole.
_TRAILING_FILLER = re.compile(
    # A connective that introduces an offer, and everything after it. "plus" is
    # deliberately absent: "Pro Line Plus" is a trim level, not a sales phrase.
    r"(\s*\b(incl|inclusief|met|voor)\b\.?.*$)|(\s*\b\d+\s*maanden?\s*$)",
    re.IGNORECASE,
)


def clean_variant(raw: str, max_length: int = 80) -> str | None:
    """The technical part of a subtitle, without the sales pitch.

    The text is cut at the first phrase that reads as an offer, any leftover
    connective tail is trimmed, and the result is capped: this is a variant
    designation, not page content.
    """
    if not raw:
        return None

    offer = _MARKETING_PHRASES.search(raw)
    specification = raw[: offer.start()] if offer else raw

    segments = re.split(r"[|•·]|\s{2,}|,", specification)
    kept = [
        segment.strip()
        for segment in segments
        if segment.strip() and not _MARKETING_PHRASES.search(segment)
    ]
    variant = " ".join(kept)
    previous = None
    while variant != previous:
        previous = variant
        variant = _TRAILING_FILLER.sub("", variant).strip(" -–—,;:")
    if not variant:
        return None
    return variant[:max_length].strip()


def parse_euro(raw: str) -> int | None:
    """A euro amount from page text, in cents. Dutch grouping."""
    match = re.search(r"€\s*([\d.  ]+(?:,\d{1,2})?)", raw)
    if not match:
        return None
    cleaned = match.group(1).replace(" ", "").replace(" ", "").replace(".", "")
    if "," in cleaned:
        cleaned = cleaned.replace(",", ".")
    try:
        amount = float(cleaned)
    except ValueError:
        return None
    if amount <= 0:
        return None
    return int(round(amount * 100))


def parse_int(raw: str, low: int, high: int) -> int | None:
    digits = re.sub(r"[^\d]", "", raw or "")
    if not digits:
        return None
    value = int(digits)
    return value if low <= value <= high else None


def observed_now() -> datetime:
    return datetime.now(UTC)
