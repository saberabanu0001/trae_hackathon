from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, datetime
from typing import Iterable

import httpx


@dataclass(frozen=True)
class ExtractedOpportunityDetails:
    deadline: date | None = None
    requires_ielts: bool | None = None
    fully_funded: bool | None = None
    minimum_gpa: float | None = None


_MONTHS = {
    "jan": 1,
    "january": 1,
    "feb": 2,
    "february": 2,
    "mar": 3,
    "march": 3,
    "apr": 4,
    "april": 4,
    "may": 5,
    "jun": 6,
    "june": 6,
    "jul": 7,
    "july": 7,
    "aug": 8,
    "august": 8,
    "sep": 9,
    "sept": 9,
    "september": 9,
    "oct": 10,
    "october": 10,
    "nov": 11,
    "november": 11,
    "dec": 12,
    "december": 12,
}


def _strip_html(text: str) -> str:
    # crude but fast; good enough for hackathon heuristics
    text = re.sub(r"(?is)<script.*?>.*?</script>", " ", text)
    text = re.sub(r"(?is)<style.*?>.*?</style>", " ", text)
    text = re.sub(r"(?s)<[^>]+>", " ", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def _find_deadline(text: str) -> date | None:
    # Try patterns like "Deadline: June 30, 2026" or "30 June 2026"
    t = text.lower()

    # month day, year
    m = re.search(
        r"\b(deadline|apply by|application deadline)\b[^a-z0-9]{0,20}"
        r"(?P<month>jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|jun(?:e)?|jul(?:y)?|aug(?:ust)?|sep(?:t)?(?:ember)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)"
        r"\s+(?P<day>\d{1,2})(?:st|nd|rd|th)?"
        r"(?:,|\s)\s*(?P<year>20\d{2})",
        t,
    )
    if m:
        month = _MONTHS.get(m.group("month"), 0)
        if month:
            return date(int(m.group("year")), month, int(m.group("day")))

    # day month year
    m2 = re.search(
        r"\b(deadline|apply by|application deadline)\b[^a-z0-9]{0,20}"
        r"(?P<day>\d{1,2})(?:st|nd|rd|th)?\s+"
        r"(?P<month>jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|jun(?:e)?|jul(?:y)?|aug(?:ust)?|sep(?:t)?(?:ember)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)"
        r"(?:,|\s)\s*(?P<year>20\d{2})",
        t,
    )
    if m2:
        month = _MONTHS.get(m2.group("month"), 0)
        if month:
            return date(int(m2.group("year")), month, int(m2.group("day")))

    # ISO date near "deadline"
    m3 = re.search(r"\b(deadline|apply by|application deadline)\b[^0-9]{0,20}(20\d{2})-(\d{2})-(\d{2})", t)
    if m3:
        try:
            return datetime.strptime(m3.group(0).split()[-1], "%Y-%m-%d").date()
        except Exception:
            return None

    return None


def _find_ielts_requirement(text: str) -> bool | None:
    t = text.lower()
    if "ielts" not in t:
        return None
    # Prefer explicit "not required" signals.
    if re.search(r"\b(ielts)\b.{0,40}\b(not required|optional|waived)\b", t):
        return False
    if re.search(r"\b(ielts required|required ielts)\b", t):
        return True
    # weak signal: mentions IELTS + minimum band
    if re.search(r"\bielts\b.{0,30}\b(\d\.\d|\d)\b", t):
        return True
    return None


def _find_funding(text: str) -> bool | None:
    t = text.lower()
    if re.search(r"\b(fully funded|full scholarship|tuition waiver|stipend)\b", t):
        return True
    if re.search(r"\b(partially funded|partial scholarship)\b", t):
        return False
    return None


def _find_min_gpa(text: str) -> float | None:
    t = text.lower()
    # patterns like "minimum GPA 3.0" or "GPA: 3.5/4.0"
    m = re.search(r"\b(minimum\s+gpa|gpa\s*minimum)\b[^0-9]{0,10}(?P<gpa>\d\.\d)", t)
    if m:
        try:
            return float(m.group("gpa"))
        except Exception:
            return None
    return None


def extract_details_from_text(text: str) -> ExtractedOpportunityDetails:
    clean = _strip_html(text)
    # Keep it bounded for speed
    snippet = clean[:50_000]
    return ExtractedOpportunityDetails(
        deadline=_find_deadline(snippet),
        requires_ielts=_find_ielts_requirement(snippet),
        fully_funded=_find_funding(snippet),
        minimum_gpa=_find_min_gpa(snippet),
    )


async def fetch_and_extract(url: str, *, timeout_s: float = 15.0) -> ExtractedOpportunityDetails | None:
    headers = {
        "User-Agent": "ApplySmartHackathonBot/0.1 (+https://example.com)",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    }
    try:
        async with httpx.AsyncClient(timeout=timeout_s, headers=headers, follow_redirects=True) as client:
            resp = await client.get(url)
            if resp.status_code >= 400:
                return None
            ctype = resp.headers.get("content-type", "")
            if "text/html" not in ctype and "application/xhtml+xml" not in ctype:
                return None
            return extract_details_from_text(resp.text)
    except Exception:
        return None


async def enrich_urls(urls: Iterable[str], *, max_concurrency: int = 4) -> dict[str, ExtractedOpportunityDetails]:
    """
    Fetch+extract a small set of URLs concurrently.
    Returns only successful extractions.
    """
    sem = httpx.AsyncClient  # placeholder to keep function small; semaphore below
    results: dict[str, ExtractedOpportunityDetails] = {}

    import asyncio

    semaphore = asyncio.Semaphore(max_concurrency)

    async def _one(u: str) -> None:
        async with semaphore:
            details = await fetch_and_extract(u)
            if details is not None:
                results[u] = details

    tasks = [asyncio.create_task(_one(u)) for u in urls]
    await asyncio.gather(*tasks, return_exceptions=True)
    return results

