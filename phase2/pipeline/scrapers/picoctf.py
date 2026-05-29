"""
PicoCTF scraper
Fetches challenges from the PicoCTF public problem archive.
No auth required.
"""

import time
import logging
import re
from typing import Iterator
import requests
from bs4 import BeautifulSoup
from schema import RawEntry

log = logging.getLogger(__name__)

# PicoCTF publishes past competition problems at this endpoint
PICOGYMS = [
    "https://play.picoctf.org/practice",
    "https://picoctf.org/index.html",
]

# Direct problem API (unofficial but stable)
PICO_API = "https://play.picoctf.org/api/challenges/"
HEADERS = {
    "User-Agent": "zero-dataset-pipeline/1.0 (research; github.com/notvcto/zero)",
    "Accept": "application/json",
}
RATE_LIMIT = 1.5


def _parse_category(cat: str) -> str:
    cat = cat.lower()
    mapping = {
        "web": "web",
        "crypto": "crypto",
        "reverse": "rev",
        "forensics": "forensics",
        "osint": "osint",
        "binary": "pwning",
        "pwn": "pwning",
        "general": "misc",
    }
    for k, v in mapping.items():
        if k in cat:
            return v
    return "unknown"


def _parse_difficulty(pts: int) -> str:
    if pts <= 100:
        return "easy"
    elif pts <= 300:
        return "medium"
    elif pts <= 500:
        return "hard"
    else:
        return "insane"


def scrape(max_challenges: int = 500) -> Iterator[RawEntry]:
    """
    Yield RawEntry objects from PicoCTF problem archive.
    Uses the public challenges API — no auth needed.
    """
    session = requests.Session()
    session.headers.update(HEADERS)

    page = 1
    fetched = 0

    while fetched < max_challenges:
        url = f"{PICO_API}?page={page}&limit=50"
        log.info(f"fetching PicoCTF page {page}")

        try:
            r = session.get(url, timeout=15)
            r.raise_for_status()
            data = r.json()
            time.sleep(RATE_LIMIT)
        except Exception as e:
            log.warning(f"PicoCTF API error: {e}")
            break

        challenges = data.get("results", data if isinstance(data, list) else [])
        if not challenges:
            log.info("no more challenges")
            break

        for ch in challenges:
            if fetched >= max_challenges:
                break

            name = ch.get("name", "")
            description = ch.get("description", "")
            category = _parse_category(ch.get("category", ""))
            pts = ch.get("points", 0)
            difficulty = _parse_difficulty(pts)
            ch_id = ch.get("id", "")
            tags = ch.get("tags", [])
            hints = ch.get("hints", [])

            # Build rich raw text including hints
            hint_text = ""
            if hints:
                hint_lines = "\n".join(f"- {h}" for h in hints)
                hint_text = f"\n\nHints:\n{hint_lines}"

            raw_text = f"{name}\n\nCategory: {category}\nPoints: {pts}\n\n{description}{hint_text}"

            if len(raw_text.strip()) < 30:
                continue

            entry = RawEntry(
                source="picoctf",
                title=name,
                url=f"https://play.picoctf.org/practice/challenge/{ch_id}",
                raw_text=raw_text,
                category=category,
                difficulty=difficulty,
                metadata={
                    "points": pts,
                    "tags": tags,
                    "challenge_id": ch_id,
                },
            )
            log.info(f"  ✓ {name[:60]} [{category}] {pts}pts")
            yield entry
            fetched += 1

        page += 1

    log.info(f"PicoCTF: total {fetched} challenges scraped")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    for i, entry in enumerate(scrape(max_challenges=10)):
        print(f"[{i}] {entry.title} | {entry.category} | {entry.difficulty}")
