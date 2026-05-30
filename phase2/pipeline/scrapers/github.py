"""
GitHub CTF writeup scraper.

Searches GitHub for repos tagged `ctf-writeups`, lists .md files,
fetches raw content, parses into structured RawEntry objects.

Auth: GITHUB_TOKEN env var (fine-grained PAT, read-only public repos)
Rate: 0.5s between requests; pause if X-RateLimit-Remaining < 100
"""

import re
import time
import logging
from pathlib import Path
from typing import Iterator

import requests

from schema import RawEntry

log = logging.getLogger(__name__)

FLAG_RE = re.compile(r'(\w+CTF\{[^}]+\}|flag\{[^}]+\}|HTB\{[^}]+\})', re.IGNORECASE)

CATEGORY_KEYWORDS = {
    "web":      ["web", "xss", "sqli", "sql injection", "csrf", "ssrf", "lfi", "rfi", "injection", "php", "flask"],
    "crypto":   ["crypto", "cryptography", "cipher", "rsa", "aes", "des", "hash", "encryption", "decrypt"],
    "rev":      ["rev", "reverse", "reversing", "disassembly", "ghidra", "ida", "decompile", "asm"],
    "forensics":["forensic", "forensics", "steganography", "stego", "memory", "pcap", "wireshark", "volatility"],
    "osint":    ["osint", "open source intelligence", "geolocation", "social media"],
    "pwning":   ["pwn", "pwning", "binary exploitation", "rop", "ret2libc", "overflow", "shellcode", "buffer"],
    "misc":     ["misc", "miscellaneous"],
}

SEARCH_QUERIES = [
    "topic:ctf-writeups",
    "topic:ctf-writeup",
]

# Repo-level blocklist: substrings to reject in repo name or description.
# Simple substring match — no regex edge cases with word boundaries.
NON_CTF_BLOCKLIST = [
    "privilege-escalation", "privilege_escalation",
    "censorship", "dictatorship",
    "cheatsheet", "cheat-sheet", "cheat_sheet",
    "awesome-list", "resource-list", "tool-list",
    "awesome-pentest", "awesome-osint", "awesome-hacking",
    "learning-path", "learning_path",
    "news", "journal", "politic",
]

MAX_FILE_SIZE = 500 * 1024  # 500KB


class GitHubScraper:
    def __init__(self, token: str, max_repos: int = 100, max_files_per_repo: int = 50):
        self.token = token
        self.max_repos = max_repos
        self.max_files_per_repo = max_files_per_repo
        self.session = requests.Session()
        if token:
            self.session.headers["Authorization"] = f"Bearer {token}"
        self.session.headers["Accept"] = "application/vnd.github+json"
        self.session.headers["X-GitHub-Api-Version"] = "2022-11-28"
        self._last_request = 0.0

    def _get(self, url: str, **kwargs) -> requests.Response | None:
        elapsed = time.monotonic() - self._last_request
        if elapsed < 0.5:
            time.sleep(0.5 - elapsed)

        try:
            resp = self.session.get(url, timeout=15, **kwargs)
            self._last_request = time.monotonic()
        except requests.RequestException as e:
            log.warning(f"Request failed: {url} — {e}")
            return None

        limit_total = int(resp.headers.get("X-RateLimit-Limit", 5000))
        remaining = int(resp.headers.get("X-RateLimit-Remaining", limit_total))
        # Pause when below 5% of this bucket's limit (handles search=30 and primary=5000 separately)
        threshold = max(5, limit_total // 20)
        if remaining < threshold:
            reset_ts = int(resp.headers.get("X-RateLimit-Reset", time.time() + 60))
            wait = max(reset_ts - time.time() + 1, 5)
            log.warning(f"Rate limit low ({remaining}/{limit_total} remaining), sleeping {wait:.0f}s")
            time.sleep(wait)

        if resp.status_code == 403:
            log.warning(f"403 on {url} — rate limited or token issue")
            return None
        if resp.status_code == 404:
            log.debug(f"404: {url}")
            return None
        if not resp.ok:
            log.warning(f"HTTP {resp.status_code} on {url}")
            return None

        return resp

    def search_repos(self) -> list[dict]:
        seen: set[str] = set()
        repos: list[dict] = []

        for query in SEARCH_QUERIES:
            resp = self._get(
                "https://api.github.com/search/repositories",
                params={"q": query, "sort": "stars", "order": "desc", "per_page": 100},
            )
            if resp is None:
                continue
            for item in resp.json().get("items", []):
                full_name = item["full_name"]
                if full_name not in seen:
                    seen.add(full_name)
                    repos.append(item)

        repos.sort(key=lambda r: r.get("stargazers_count", 0), reverse=True)

        filtered = []
        for r in repos:
            haystack = (r.get("name", "") + " " + (r.get("description") or "")).lower()
            if any(kw in haystack for kw in NON_CTF_BLOCKLIST):
                log.debug(f"Skipping non-CTF repo: {r['full_name']}")
                continue
            filtered.append(r)

        return filtered[: self.max_repos]

    def list_md_files(self, owner: str, repo: str, branch: str) -> list[dict]:
        resp = self._get(
            f"https://api.github.com/repos/{owner}/{repo}/git/trees/{branch}",
            params={"recursive": "1"},
        )
        if resp is None:
            return []

        data = resp.json()
        if data.get("truncated"):
            log.debug(f"{owner}/{repo}: tree truncated")

        files = []
        for item in data.get("tree", []):
            path = item.get("path", "")
            if not path.lower().endswith(".md"):
                continue
            # Skip root README
            if path.lower() == "readme.md":
                continue
            if item.get("size", 0) > MAX_FILE_SIZE:
                log.debug(f"Skipping large file: {path}")
                continue
            files.append({"path": path, "sha": item.get("sha")})

        return files[: self.max_files_per_repo]

    def fetch_raw(self, owner: str, repo: str, branch: str, path: str) -> str | None:
        url = f"https://raw.githubusercontent.com/{owner}/{repo}/{branch}/{path}"
        resp = self._get(url)
        return resp.text if resp is not None else None

    def _detect_category(self, path: str, content: str) -> str:
        haystack = (path + " " + content[:1000]).lower()
        for cat, keywords in CATEGORY_KEYWORDS.items():
            if any(kw in haystack for kw in keywords):
                return cat
        return "misc"

    def _is_english(self, text: str) -> bool:
        sample = text[:200]
        if not sample:
            return True
        non_ascii = sum(1 for c in sample if ord(c) > 127)
        return (non_ascii / len(sample)) <= 0.30

    def _parse_markdown(self, content: str) -> dict | None:
        if len(content) < 300:
            return None
        if "##" not in content:
            return None
        if not self._is_english(content):
            return None

        # Require at least one flag pattern — hard gate for non-writeup files
        flag_match = FLAG_RE.search(content)
        if flag_match is None:
            return None
        flag = flag_match.group(1)

        pre_flag = content[: flag_match.start()]
        if len([l for l in pre_flag.splitlines() if l.strip()]) < 3:
            return None

        # Split into sections on ## headers
        sections = re.split(r"^##+ ", content, flags=re.MULTILINE)
        sections = [s.strip() for s in sections if s.strip()]

        if len(sections) < 2:
            return None

        boilerplate_headers = {"introduction", "overview", "about", "writeup", "solution", "flag", "answer"}
        challenge = ""
        steps = []

        for sec in sections:
            header = sec.split("\n")[0].lower().strip().rstrip(":")
            if not challenge and header not in boilerplate_headers:
                challenge = sec
            else:
                steps.append(sec)

        if not challenge:
            challenge = sections[0]
            steps = sections[1:]

        return {"challenge": challenge, "steps": steps, "flag": flag}

    def _scrape_repo(self, repo: dict) -> Iterator[RawEntry]:
        full_name = repo["full_name"]
        owner, name = full_name.split("/", 1)
        stars = repo.get("stargazers_count", 0)
        branch = repo.get("default_branch", "main")

        log.info(f"  Scanning {full_name} ({stars}★)")

        md_files = self.list_md_files(owner, name, branch)
        log.debug(f"    {len(md_files)} .md files")

        for file_info in md_files:
            path = file_info["path"]
            content = self.fetch_raw(owner, name, branch, path)
            if content is None:
                continue

            parsed = self._parse_markdown(content)
            if parsed is None:
                log.debug(f"    Skipped (quality): {path}")
                continue

            challenge_name = Path(path).stem.replace("-", " ").replace("_", " ").title()
            steps_text = "\n\n".join(parsed["steps"])
            raw_text = f"{parsed['challenge']}\n\n{steps_text}".strip()

            yield RawEntry(
                source="github",
                title=f"{name} — {challenge_name}",
                url=f"https://github.com/{owner}/{name}/blob/{branch}/{path}",
                raw_text=raw_text,
                category=self._detect_category(path, content),
                difficulty="unknown",
                flag=parsed["flag"],
                metadata={
                    "repo": full_name,
                    "stars": stars,
                    "path": path,
                },
            )

    def scrape(self) -> Iterator[RawEntry]:
        repos = self.search_repos()
        log.info(f"Found {len(repos)} repos to scan")
        for repo in repos:
            yield from self._scrape_repo(repo)


def scrape(token: str, max_repos: int = 100, max_files_per_repo: int = 50) -> Iterator[RawEntry]:
    scraper = GitHubScraper(token, max_repos=max_repos, max_files_per_repo=max_files_per_repo)
    yield from scraper.scrape()
