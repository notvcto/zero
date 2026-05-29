"""
CTFtime scraper
Fetches writeup listings and full writeup text.
Requires: CTFTIME_SESSION cookie
"""

import os
import re
import time
import logging
from typing import Iterator
import requests
from bs4 import BeautifulSoup
from schema import RawEntry

log = logging.getLogger(__name__)

BASE = "https://ctftime.org"
WRITEUPS_URL = f"{BASE}/writeups"
HEADERS = {
    "User-Agent": "zero-dataset-pipeline/1.0 (research; github.com/notvcto/zero)",
    "Accept": "text/html,application/xhtml+xml",
}
RATE_LIMIT = 2.0  # seconds between requests


def _session(cookie: str) -> requests.Session:
    s = requests.Session()
    s.headers.update(HEADERS)
    s.cookies.set("sessionid", cookie, domain="ctftime.org")
    return s


def _get(session: requests.Session, url: str) -> BeautifulSoup | None:
    try:
        r = session.get(url, timeout=15)
        r.raise_for_status()
        time.sleep(RATE_LIMIT)
        return BeautifulSoup(r.text, "html.parser")
    except Exception as e:
        log.warning(f"fetch failed {url}: {e}")
        return None


def _parse_category(text: str) -> str:
    text = text.lower()
    mapping = {
        "web": "web",
        "crypto": "crypto",
        "rev": "rev",
        "reverse": "rev",
        "forensic": "forensics",
        "osint": "osint",
        "pwn": "pwning",
        "binary": "pwning",
        "misc": "misc",
    }
    for k, v in mapping.items():
        if k in text:
            return v
    return "unknown"


def _parse_writeup_page(soup: BeautifulSoup, url: str, title: str, category: str) -> RawEntry | None:
    """Extract raw text from a single writeup page."""
    # Must be an actual writeup URL, not an event page
    if "/event/" in url and "/writeup/" not in url:
        log.debug(f"skipping event page (not a writeup): {url}")
        return None

    content = (
        soup.find("div", class_="well")
        or soup.find("article")
        or soup.find("div", id="content")
    )
    if not content:
        log.warning(f"no content block found at {url}")
        return None

    raw_text = content.get_text(separator="\n", strip=True)
    if len(raw_text) < 200:
        return None

    # Try to find flag
    flag = None
    flag_match = re.search(r"(flag\{[^}]+\}|CTF\{[^}]+\}|picoCTF\{[^}]+\}|\w+CTF\{[^}]+\})", raw_text, re.IGNORECASE)
    if flag_match:
        flag = flag_match.group(1)

    return RawEntry(
        source="ctftime",
        title=title,
        url=url,
        raw_text=raw_text,
        category=category,
        flag=flag,
        metadata={"scraped_from": "ctftime"},
    )


def scrape(cookie: str, max_pages: int = 20, max_per_page: int = 50) -> Iterator[RawEntry]:
    """
    Yield RawEntry objects from CTFtime writeups.
    Paginates through the writeup listing.
    Each row has two links: event page (/event/<id>) and writeup (/writeup/<id>).
    We grab the writeup link only.
    """
    session = _session(cookie)
    page = 1

    while page <= max_pages:
        url = f"{WRITEUPS_URL}/?page={page}"
        log.info(f"fetching CTFtime page {page}: {url}")
        soup = _get(session, url)
        if not soup:
            break

        rows = soup.select("table.table tbody tr")
        if not rows:
            log.info("no more rows, stopping CTFtime scrape")
            break

        fetched = 0
        for row in rows[:max_per_page]:
            cells = row.find_all("td")
            if len(cells) < 3:
                continue

            # Row structure: cells[0]=event, cells[1]=task, cells[2]=?, cells[3]=team, cells[4]=writeup
            if len(cells) < 5:
                continue
            title_tag = cells[0].find("a")
            writeup_tag = cells[4].find("a")
            if not title_tag or not writeup_tag:
                continue

            title = f"{title_tag.get_text(strip=True)} — {cells[1].get_text(strip=True)}"
            href = writeup_tag.get("href", "")
            if not href.startswith("http"):
                href = BASE + href

            # category from task name (cells[1])
            cat_text = cells[1].get_text(strip=True)
            category = _parse_category(cat_text)

            writeup_soup = _get(session, href)
            if not writeup_soup:
                continue

            entry = _parse_writeup_page(writeup_soup, href, title, category)
            if entry:
                log.info(f"  ✓ {title[:60]} [{category}]")
                yield entry
                fetched += 1

        log.info(f"page {page}: fetched {fetched} entries")
        page += 1


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    cookie = os.environ["CTFTIME_SESSION"]
    for i, entry in enumerate(scrape(cookie, max_pages=2, max_per_page=5)):
        print(f"[{i}] {entry.title} | {entry.category} | {len(entry.raw_text)} chars")
