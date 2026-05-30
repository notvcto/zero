"""
Zero Dataset Pipeline — Orchestrator
Phase 2: Seed Dataset Construction

Usage:
    python run.py                          # full pipeline
    python run.py --sources github         # single source
    python run.py --scrape-only --no-push  # no HF push
    python run.py --no-push                # skip HF upload

Env vars (or .env file):
    GITHUB_TOKEN     GitHub fine-grained PAT (read-only public repos)
    HTB_TOKEN        HackTheBox App Token
    HF_TOKEN         HuggingFace write token
"""

import os
import sys
import argparse
import logging
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

sys.path.insert(0, str(Path(__file__).parent))

from schema import Triple, RawEntry
from pipeline.scrapers import github, htb_official, htb_community
from pipeline.normalize import normalize
from pipeline.inject import inject
from pipeline.validate import Validator
from pipeline.push import push

log = logging.getLogger(__name__)


def setup_logging(level: str = "INFO"):
    logging.basicConfig(
        level=getattr(logging, level),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )


def parse_args():
    p = argparse.ArgumentParser(description="Zero dataset pipeline")
    p.add_argument(
        "--sources",
        nargs="+",
        choices=["github", "htb_official", "htb_community"],
        default=["github", "htb_official", "htb_community"],
        help="Which sources to scrape (default: all)",
    )
    p.add_argument("--scrape-only", action="store_true", help="Scrape + normalize only, skip HF push")
    p.add_argument("--no-push", action="store_true", help="Skip HuggingFace upload")
    p.add_argument("--output", default="data/seed.jsonl", help="Output JSONL path")
    p.add_argument("--max-github-repos", type=int, default=100)
    p.add_argument("--max-files-per-repo", type=int, default=50)
    p.add_argument("--max-htb-machines", type=int, default=200)
    p.add_argument("--max-oxdf", type=int, default=100)
    p.add_argument("--max-ippsec", type=int, default=50)
    p.add_argument("--log-level", default="INFO")
    return p.parse_args()


def check_env(sources: list[str], no_push: bool):
    missing = []
    if "github" in sources and not os.environ.get("GITHUB_TOKEN"):
        missing.append("GITHUB_TOKEN (optional — unauthenticated rate limit is 60 req/hour)")
    if ("htb_official" in sources or "htb_community" in sources) and not os.environ.get("HTB_TOKEN"):
        missing.append("HTB_TOKEN (optional for htb_community)")
    if not no_push and not os.environ.get("HF_TOKEN"):
        missing.append("HF_TOKEN")

    hard_missing = [m for m in missing if "optional" not in m]
    if hard_missing:
        log.error(f"Missing required env vars: {', '.join(hard_missing)}")
        log.error("Copy .env.example to .env and fill in your credentials.")
        sys.exit(1)
    for m in missing:
        log.warning(f"Optional env var not set: {m}")


def iter_raw_entries(sources: list[str], args) -> iter:
    if "github" in sources:
        log.info("=== GitHub ===")
        token = os.environ.get("GITHUB_TOKEN", "")
        yield from github.scrape(
            token,
            max_repos=args.max_github_repos,
            max_files_per_repo=args.max_files_per_repo,
        )

    if "htb_official" in sources:
        log.info("=== HTB Official ===")
        token = os.environ.get("HTB_TOKEN", "")
        yield from htb_official.scrape(token, max_machines=args.max_htb_machines)

    if "htb_community" in sources:
        log.info("=== HTB Community ===")
        yield from htb_community.scrape(
            max_oxdf=args.max_oxdf,
            max_ippsec=args.max_ippsec,
        )


def process_entry(entry: RawEntry) -> Triple | None:
    normalized = normalize(entry)
    if not normalized["challenge"].strip():
        log.debug(f"skipping empty challenge: {entry.title}")
        return None

    normalized, is_abstention = inject(entry, normalized)

    steps_text = "\n\n".join(normalized.get("steps_raw", [])) or ""
    triple = Triple(
        id=Triple.make_id(entry.source, entry.title, entry.url),
        source=entry.source,
        category=entry.category,
        difficulty=entry.difficulty,
        challenge=normalized["challenge"],
        reasoning_chain=steps_text or normalized.get("solution_hint", ""),
        solution=normalized.get("solution_hint", "") or normalized.get("flag", "unknown"),
        flag=normalized.get("flag"),
        abstention=is_abstention,
        metadata={**entry.metadata, "title": entry.title, "url": entry.url},
    )
    return triple


def main():
    args = parse_args()
    setup_logging(args.log_level)

    no_push = args.no_push or args.scrape_only

    log.info("Zero Dataset Pipeline — Phase 2")
    log.info(f"Sources: {', '.join(args.sources)}")
    log.info(f"Output:  {args.output}")

    check_env(args.sources, no_push)

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    validator = Validator()
    total_raw = 0
    total_written = 0

    with open(output_path, "w", encoding="utf-8") as out_f:
        for entry in iter_raw_entries(args.sources, args):
            total_raw += 1

            triple = process_entry(entry)
            if triple is None:
                continue

            if validator.accept(triple):
                out_f.write(triple.to_jsonl() + "\n")
                out_f.flush()
                total_written += 1

                if total_written % 50 == 0:
                    log.info(f"  → {total_written} triples written so far")

    log.info("")
    log.info("=== Pipeline complete ===")
    log.info(f"Raw entries scraped:  {total_raw}")
    log.info(f"Triples written:      {total_written}")
    log.info(validator.report())

    if total_written == 0:
        log.error("No triples written — check scraper output and env vars")
        sys.exit(1)

    if not no_push:
        log.info("Pushing to HuggingFace Hub...")
        url = push(str(output_path))
        log.info(f"Dataset live: {url}")
    else:
        log.info("Skipping HF push (--no-push or --scrape-only)")

    log.info(f"Output: {output_path} ({total_written} triples)")


if __name__ == "__main__":
    main()
