"""
HTB community writeups scraper
Sources:
  - 0xdf blog: https://0xdf.gitlab.io
  - IppSec YouTube transcripts via yt-dlp
No auth required for 0xdf. yt-dlp handles YouTube.
"""

import re
import time
import logging
import subprocess
import json
import tempfile
import os
from typing import Iterator
import requests
from bs4 import BeautifulSoup
from schema import RawEntry

log = logging.getLogger(__name__)

OXDF_BASE = "https://0xdf.gitlab.io"
OXDF_FEED = f"{OXDF_BASE}/feed.xml"
IPPSEC_CHANNEL = "https://www.youtube.com/@ippsec"
HEADERS = {
    "User-Agent": "zero-dataset-pipeline/1.0 (research; github.com/notvcto/zero)",
    "Accept": "text/html,application/xml,application/xhtml+xml",
}
RATE_LIMIT = 2.0


def _get(url: str) -> BeautifulSoup | None:
    try:
        r = requests.get(url, headers=HEADERS, timeout=15)
        r.raise_for_status()
        time.sleep(RATE_LIMIT)
        return BeautifulSoup(r.text, "html.parser")
    except Exception as e:
        log.warning(f"fetch failed {url}: {e}")
        return None


def _get_xml(url: str) -> BeautifulSoup | None:
    try:
        r = requests.get(url, headers=HEADERS, timeout=15)
        r.raise_for_status()
        time.sleep(RATE_LIMIT)
        return BeautifulSoup(r.text, "xml")
    except Exception as e:
        log.warning(f"xml fetch failed {url}: {e}")
        return None


def _parse_difficulty(title: str, tags: list) -> str:
    text = (title + " " + " ".join(tags)).lower()
    if "easy" in text:
        return "easy"
    if "medium" in text:
        return "medium"
    if "hard" in text:
        return "hard"
    if "insane" in text:
        return "insane"
    return "unknown"


def _parse_category_from_tags(tags: list) -> str:
    tag_text = " ".join(tags).lower()
    mapping = {
        "web": "web",
        "crypto": "crypto",
        "rev": "rev",
        "forensic": "forensics",
        "osint": "osint",
        "pwn": "pwning",
        "active-directory": "pwning",
        "linux": "misc",
        "windows": "misc",
    }
    for k, v in mapping.items():
        if k in tag_text:
            return v
    return "misc"


def _extract_flag(text: str) -> str | None:
    match = re.search(r"(HTB\{[^}]+\}|flag\{[^}]+\})", text, re.IGNORECASE)
    return match.group(1) if match else None


# ─── 0xdf ────────────────────────────────────────────────────────────────────

def _scrape_oxdf_index() -> list[dict]:
    """Return list of {title, url, tags} from 0xdf's HTB posts."""
    entries = []

    # Primary: tags.html — Jekyll site with id="hackthebox" h2 section
    soup = _get(f"{OXDF_BASE}/tags.html")
    if soup:
        # h2 has text like "hackthebox[570]" with a <small> child — match by id
        htb_section = soup.find("h2", id="hackthebox")
        if htb_section:
            ul = htb_section.find_next_sibling("ul")
            if ul:
                for li in ul.find_all("li"):
                    a = li.find("a")
                    if a:
                        href = a.get("href", "")
                        if not href.startswith("http"):
                            href = OXDF_BASE + href
                        entries.append({
                            "title": a.get_text(strip=True),
                            "url": href,
                            "tags": ["hackthebox"],
                        })
        if entries:
            return entries

    # Fallback: Atom feed (only ~10 most recent posts)
    log.warning("tags.html parse failed, falling back to Atom feed")
    soup = _get_xml(OXDF_FEED)
    if not soup:
        return entries
    for entry in soup.find_all("entry")[:200]:
        title_tag = entry.find("title")
        title = title_tag.get_text(strip=True) if title_tag else ""
        link_tag = entry.find("link", rel="alternate") or entry.find("link")
        link = link_tag.get("href", "") if link_tag else ""
        cats = [c.get("term", "").lower() for c in entry.find_all("category")]
        if "hackthebox" in cats or "htb" in " ".join(cats):
            entries.append({"title": title, "url": link, "tags": cats})

    return entries


def _scrape_oxdf_post(url: str, title: str, tags: list) -> RawEntry | None:
    soup = _get(url)
    if not soup:
        return None

    # 0xdf posts are in <div class="post-content">
    content = soup.find("div", class_="post-content") or soup.find("article")
    if not content:
        return None

    raw_text = content.get_text(separator="\n", strip=True)
    if len(raw_text) < 200:
        return None

    # Extract difficulty from post tags
    post_tags = [t.get_text(strip=True).lower() for t in soup.find_all("a", class_="tag")]
    all_tags = tags + post_tags
    difficulty = _parse_difficulty(title, all_tags)
    category = _parse_category_from_tags(all_tags)
    flag = _extract_flag(raw_text)

    return RawEntry(
        source="htb_community",
        title=title,
        url=url,
        raw_text=raw_text,
        category=category,
        difficulty=difficulty,
        flag=flag,
        metadata={"author": "0xdf", "tags": all_tags},
    )


def scrape_oxdf(max_posts: int = 100) -> Iterator[RawEntry]:
    log.info("scraping 0xdf HTB writeups...")
    index = _scrape_oxdf_index()
    log.info(f"found {len(index)} 0xdf HTB posts")

    for i, post in enumerate(index[:max_posts]):
        entry = _scrape_oxdf_post(post["url"], post["title"], post.get("tags", []))
        if entry:
            log.info(f"  ✓ 0xdf: {entry.title[:60]} [{entry.category}]")
            yield entry


# ─── IppSec ──────────────────────────────────────────────────────────────────

def _yt_dlp_available() -> bool:
    try:
        subprocess.run(["yt-dlp", "--version"], capture_output=True, check=True)
        return True
    except (subprocess.CalledProcessError, FileNotFoundError):
        return False


def _get_ippsec_videos(max_videos: int) -> list[dict]:
    """Use yt-dlp to list IppSec videos."""
    try:
        result = subprocess.run(
            [
                "yt-dlp",
                "--flat-playlist",
                "--print", "%(id)s\t%(title)s",
                "--max-downloads", str(max_videos),
                "https://www.youtube.com/@ippsec/videos",
            ],
            capture_output=True,
            text=True,
            timeout=60,
        )
        videos = []
        for line in result.stdout.strip().splitlines():
            parts = line.split("\t", 1)
            if len(parts) == 2:
                videos.append({"id": parts[0], "title": parts[1]})
        return videos
    except Exception as e:
        log.warning(f"yt-dlp list failed: {e}")
        return []


def _clean_vtt(vtt: str) -> str:
    """Parse a VTT subtitle file into clean prose."""
    # Strip inline timestamp tags: <00:00:00.480>, <c>, </c>, <00:00:00.480><c>, etc.
    tag_re = re.compile(r"<[^>]+>")
    seen = []
    for line in vtt.splitlines():
        line = line.strip()
        # Skip blank lines, WEBVTT header, NOTE blocks, cue timestamps, and
        # metadata lines like "Kind: captions" / "Language: en"
        if not line:
            continue
        if line.startswith("WEBVTT") or line.startswith("NOTE") or line.startswith("Kind:") or line.startswith("Language:"):
            continue
        if "-->" in line:
            continue
        # Skip pure numeric cue IDs
        if line.isdigit():
            continue
        # Strip all remaining inline VTT tags
        line = tag_re.sub("", line).strip()
        if not line:
            continue
        # Deduplicate consecutive identical lines (VTT word-by-word captions repeat)
        if not seen or seen[-1] != line:
            seen.append(line)
    return " ".join(seen)


def _fetch_transcript(video_id: str) -> str | None:
    """Fetch auto-generated subtitles for a YouTube video."""
    try:
        with tempfile.TemporaryDirectory() as tmpdir:
            result = subprocess.run(
                [
                    "yt-dlp",
                    "--write-auto-sub",
                    "--sub-lang", "en",
                    "--sub-format", "vtt",
                    "--skip-download",
                    "--output", os.path.join(tmpdir, "%(id)s.%(ext)s"),
                    f"https://www.youtube.com/watch?v={video_id}",
                ],
                capture_output=True,
                text=True,
                timeout=60,
            )

            # Find the VTT file
            for fname in os.listdir(tmpdir):
                if fname.endswith(".vtt"):
                    with open(os.path.join(tmpdir, fname)) as f:
                        vtt = f.read()
                    return _clean_vtt(vtt)
    except Exception as e:
        log.warning(f"transcript fetch failed {video_id}: {e}")
    return None


def scrape_ippsec(max_videos: int = 50) -> Iterator[RawEntry]:
    if max_videos == 0:
        return
    if not _yt_dlp_available():
        log.warning("yt-dlp not available, skipping IppSec scrape. Install with: pip install yt-dlp")
        return

    log.info("scraping IppSec YouTube transcripts...")
    videos = _get_ippsec_videos(max_videos)[:max_videos]
    log.info(f"found {len(videos)} IppSec videos (limit: {max_videos})")

    for video in videos:
        vid_id = video["id"]
        title = video["title"]

        transcript = _fetch_transcript(vid_id)
        if not transcript or len(transcript) < 200:
            continue

        # IppSec titles are usually "HackTheBox - MachineName"
        machine_name = re.sub(r"HackTheBox\s*[-–]\s*", "", title, flags=re.IGNORECASE).strip()
        difficulty = _parse_difficulty(transcript, [])
        category = _parse_category_from_tags(transcript.lower().split()[:100])

        raw_text = f"Machine: {machine_name}\nSource: IppSec walkthrough (YouTube)\n\nTranscript:\n{transcript}"

        entry = RawEntry(
            source="htb_community",
            title=machine_name,
            url=f"https://www.youtube.com/watch?v={vid_id}",
            raw_text=raw_text,
            category=category,
            difficulty=difficulty,
            metadata={"author": "ippsec", "video_id": vid_id},
        )
        log.info(f"  ✓ IppSec: {machine_name[:60]} [{category}]")
        yield entry
        time.sleep(1)


# ─── Combined ────────────────────────────────────────────────────────────────

def scrape(max_oxdf: int = 100, max_ippsec: int = 50) -> Iterator[RawEntry]:
    yield from scrape_oxdf(max_posts=max_oxdf)
    if max_ippsec is not None:
        yield from scrape_ippsec(max_videos=max_ippsec)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    for i, entry in enumerate(scrape(max_oxdf=3, max_ippsec=0)):
        print(f"[{i}] {entry.title} | {entry.category} | {entry.metadata.get('author')}")
        print(entry.raw_text[:300])
        print("---")
