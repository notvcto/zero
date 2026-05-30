"""
HTB Official API scraper
Fetches retired machine writeups via the HTB v4 API.
Requires: HTB_TOKEN (App Token from Profile Settings)
"""

import os
import time
import logging
from typing import Iterator
import requests
from schema import RawEntry

log = logging.getLogger(__name__)

API_BASE = "https://labs.hackthebox.com/api/v4"
HEADERS = {
    "User-Agent": "zero-dataset-pipeline/1.0 (research; github.com/notvcto/zero)",
    "Accept": "application/json",
}
RATE_LIMIT = 1.5


def _session(token: str) -> requests.Session:
    s = requests.Session()
    s.headers.update(HEADERS)
    s.headers["Authorization"] = f"Bearer {token}"
    return s


def _get(session: requests.Session, url: str, params: dict = None) -> dict | None:
    try:
        r = session.get(url, params=params, timeout=15)
        r.raise_for_status()
        time.sleep(RATE_LIMIT)
        return r.json()
    except Exception as e:
        log.warning(f"HTB API error {url}: {e}")
        return None


def _parse_difficulty(diff: str) -> str:
    d = (diff or "").lower()
    if "easy" in d:
        return "easy"
    if "medium" in d:
        return "medium"
    if "hard" in d:
        return "hard"
    if "insane" in d:
        return "insane"
    return "unknown"


def _parse_category(os_name: str, tags: list) -> str:
    """HTB machines are OS-based, but we derive category from tags."""
    tag_text = " ".join(t.get("name", "") for t in (tags or [])).lower()
    if "web" in tag_text:
        return "web"
    if "crypto" in tag_text:
        return "crypto"
    if "reverse" in tag_text or "re" in tag_text:
        return "rev"
    if "forensic" in tag_text:
        return "forensics"
    if "osint" in tag_text:
        return "osint"
    if "active directory" in tag_text or "privesc" in tag_text:
        return "pwning"
    return "misc"


def _build_raw_text(machine: dict) -> str:
    """Build raw text from machine profile metadata (no writeup — VIP-only)."""
    name = machine.get("name", "")
    os_name = machine.get("os", "")
    difficulty = machine.get("difficultyText", "")
    user_owns = machine.get("user_owns_count", 0)
    root_owns = machine.get("root_owns_count", 0)

    lines = [
        f"Machine: {name}",
        f"OS: {os_name}",
        f"Difficulty: {difficulty}",
        f"User owns: {user_owns} | Root owns: {root_owns}",
        "",
    ]

    tags = machine.get("tags", [])
    if tags:
        tag_names = [t.get("name", "") for t in tags]
        lines.append(f"Techniques: {', '.join(tag_names)}")

    return "\n".join(lines)


def scrape(token: str, max_machines: int = 200) -> Iterator[RawEntry]:
    """
    Yield RawEntry objects from retired HTB machines.
    Fetches machine list then fetches writeup for each retired machine.
    """
    session = _session(token)

    # Get retired machines list
    log.info("fetching HTB retired machines list...")
    data = _get(session, f"{API_BASE}/machine/list/retired/paginated", params={"per_page": 100, "page": 1})
    if not data:
        log.error("failed to fetch HTB retired machines")
        return

    machines = data.get("data", [])
    total_pages = data.get("meta", {}).get("last_page", 1)
    log.info(f"found {len(machines)} machines on page 1 of {total_pages}")

    fetched = 0
    page = 1

    while fetched < max_machines and page <= total_pages:
        if page > 1:
            data = _get(session, f"{API_BASE}/machine/list/retired/paginated", params={"per_page": 100, "page": page})
            if not data:
                break
            machines = data.get("data", [])

        for machine in machines:
            if fetched >= max_machines:
                break

            machine_id = machine.get("id")
            name = machine.get("name", "")
            difficulty = _parse_difficulty(machine.get("difficultyText", ""))
            os_name = machine.get("os", "")

            # Fetch full machine profile for tags
            profile = _get(session, f"{API_BASE}/machine/profile/{name}")
            machine_full = profile.get("info", machine) if profile else machine
            tags = machine_full.get("tags", [])
            category = _parse_category(os_name, tags)

            raw_text = _build_raw_text(machine_full)

            if len(raw_text.strip()) < 50:
                continue

            entry = RawEntry(
                source="htb_official",
                title=name,
                url=f"https://app.hackthebox.com/machines/{name}",
                raw_text=raw_text,
                category=category,
                difficulty=difficulty,
                metadata={
                    "machine_id": machine_id,
                    "os": os_name,
                    "has_writeup": False,
                },
            )
            log.info(f"  ✓ {name} [{category}] [{difficulty}]")
            yield entry
            fetched += 1

        page += 1

    log.info(f"HTB official: total {fetched} machines scraped")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    token = os.environ["HTB_TOKEN"]
    for i, entry in enumerate(scrape(token, max_machines=5)):
        print(f"[{i}] {entry.title} | {entry.category} | {entry.difficulty}")
        print(entry.raw_text[:300])
        print("---")
