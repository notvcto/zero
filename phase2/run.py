"""
Zero Dataset Pipeline — Orchestrator
Phase 2: Seed Dataset Construction

Usage:
    python run.py                          # full pipeline
    python run.py --sources ctftime        # single source
    python run.py --dry-run                # no Claude API calls, no HF push
    python run.py --no-push                # skip HF upload

Env vars (or .env file):
    CTFTIME_SESSION    CTFtime session cookie
    HTB_TOKEN          HackTheBox App Token
    ANTHROPIC_API_KEY  Anthropic API key
    HF_TOKEN           HuggingFace write token
"""

import os
import sys
import argparse
import logging
import json
from pathlib import Path
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

# Add phase2 to path
sys.path.insert(0, str(Path(__file__).parent))

from schema import Triple, RawEntry
from pipeline.scrapers import ctftime, picoctf, htb_official, htb_community
from pipeline.normalize import normalize
from pipeline.enrich import enrich
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
        choices=["ctftime", "picoctf", "htb_official", "htb_community"],
        default=["ctftime", "picoctf", "htb_official", "htb_community"],
        help="Which sources to scrape (default: all)",
    )
    p.add_argument("--scrape-only", action="store_true", help="Scrape + normalize only, write raw.jsonl for manual enrichment via Claude Code")
    p.add_argument("--dry-run", action="store_true", help="Scrape only, no HF push (alias for --scrape-only --no-push)")
    p.add_argument("--no-push", action="store_true", help="Skip HuggingFace upload")
    p.add_argument("--output", default="data/seed.jsonl", help="Output JSONL path")
    p.add_argument("--max-ctftime-pages", type=int, default=20)
    p.add_argument("--max-pico", type=int, default=500)
    p.add_argument("--max-htb-machines", type=int, default=200)
    p.add_argument("--max-oxdf", type=int, default=100)
    p.add_argument("--max-ippsec", type=int, default=50)
    p.add_argument("--log-level", default="INFO")
    return p.parse_args()


def check_env(sources: list[str], dry_run: bool, no_push: bool):
    missing = []
    if "ctftime" in sources and not os.environ.get("CTFTIME_SESSION"):
        missing.append("CTFTIME_SESSION")
    if ("htb_official" in sources or "htb_community" in sources) and not os.environ.get("HTB_TOKEN"):
        missing.append("HTB_TOKEN (optional for htb_community)")
    if not no_push and not os.environ.get("HF_TOKEN"):
        missing.append("HF_TOKEN")

    hard_missing = [m for m in missing if "optional" not in m]
    if hard_missing:
        log.error(f"Missing required env vars: {', '.join(hard_missing)}")
        log.error("Copy .env.example to .env and fill in your credentials.")
        sys.exit(1)
    if missing:
        for m in missing:
            log.warning(f"Optional env var not set: {m}")


def iter_raw_entries(sources: list[str], args) -> iter:
    """Yield RawEntry objects from all configured sources."""
    if "ctftime" in sources:
        log.info("=== CTFtime ===")
        cookie = os.environ.get("CTFTIME_SESSION", "")
        yield from ctftime.scrape(cookie, max_pages=args.max_ctftime_pages)

    if "picoctf" in sources:
        log.info("=== PicoCTF ===")
        yield from picoctf.scrape(max_challenges=args.max_pico)

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


def process_entry(entry: RawEntry, dry_run: bool) -> Triple | None:
    """Full pipeline for a single entry: normalize → inject → enrich → validate."""
    # 1. Normalize
    normalized = normalize(entry)
    if not normalized["challenge"].strip():
        log.debug(f"skipping empty challenge: {entry.title}")
        return None

    # 2. Uncertainty injection
    normalized, is_abstention = inject(entry, normalized)

    # 3. Enrich (skip in dry-run)
    if dry_run:
        enriched = {
            "challenge": normalized["challenge"],
            "reasoning_chain": "[DRY RUN - no Claude call]",
            "solution": normalized.get("solution_hint", "") or "unknown",
        }
    else:
        enriched = enrich(entry, normalized, abstention=is_abstention)
        if enriched is None:
            return None

    # 4. Build triple
    triple = Triple(
        id=Triple.make_id(entry.source, entry.title, entry.url),
        source=entry.source,
        category=entry.category,
        difficulty=entry.difficulty,
        challenge=enriched["challenge"],
        reasoning_chain=enriched["reasoning_chain"],
        solution=enriched["solution"],
        flag=normalized.get("flag"),
        abstention=is_abstention,
        metadata={
            **entry.metadata,
            "title": entry.title,
            "url": entry.url,
        },
    )
    return triple


def main():
    args = parse_args()
    setup_logging(args.log_level)

    log.info("Zero Dataset Pipeline — Phase 2")
    log.info(f"Sources: {', '.join(args.sources)}")
    log.info(f"Output:  {args.output}")
    if args.dry_run:
        log.info("DRY RUN — Claude API and HF push disabled")

    check_env(args.sources, args.dry_run, args.no_push)

    # Ensure output directory exists
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    validator = Validator()
    total_raw = 0
    total_written = 0

    with open(output_path, "w", encoding="utf-8") as out_f:
        for entry in iter_raw_entries(args.sources, args):
            total_raw += 1

            triple = process_entry(entry, args.dry_run)
            if triple is None:
                continue

            if validator.accept(triple):
                out_f.write(triple.to_jsonl() + "\n")
                out_f.flush()
                total_written += 1

                if total_written % 50 == 0:
                    log.info(f"  → {total_written} triples written so far")

    log.info("")
    log.info(f"=== Pipeline complete ===")
    log.info(f"Raw entries scraped:  {total_raw}")
    log.info(f"Triples written:      {total_written}")
    log.info(validator.report())

    if total_written == 0:
        log.error("No triples written — check scraper output and env vars")
        sys.exit(1)

    # Push to HF Hub
    if not args.no_push and not args.dry_run:
        log.info(f"Pushing to HuggingFace Hub...")
        url = push(str(output_path))
        log.info(f"Dataset live: {url}")
    else:
        log.info("Skipping HF push (--no-push or --dry-run)")

    log.info(f"Output: {output_path} ({total_written} triples)")


if __name__ == "__main__":
    main()
