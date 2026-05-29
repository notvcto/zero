# Phase 2 — Seed Dataset Construction

This directory contains the data pipeline for building Zero's seed training corpus.

## Overview

The pipeline scrapes CTF writeups and security challenges from four sources,
normalizes them into structured triples, enriches the reasoning chain via Claude,
and publishes the final dataset to HuggingFace.

```
phase2/
  pipeline/
    scrapers/
      ctftime.py        CTFtime writeup scraper
      picoctf.py        PicoCTF problem archive
      htb_official.py   HTB API (retired machines)
      htb_community.py  0xdf blog + IppSec transcripts
    normalize.py        Extract structure from raw text
    enrich.py           Claude hybrid reasoning chain generation
    inject.py           Uncertainty injection (10% abstention triples)
    validate.py         Schema validation + deduplication
    push.py             HuggingFace Hub upload
  run.py                Pipeline orchestrator
  schema.py             Triple dataclass + validators
  .env.example          Credential template
  requirements.txt
```

## Triple Schema

Each training sample is a triple:

```json
{
  "id": "abc123def456789a",
  "source": "ctftime",
  "category": "web",
  "difficulty": "medium",
  "challenge": "Clean problem statement...",
  "reasoning_chain": "Step-by-step reasoning in Zero's voice...",
  "solution": "Final answer / flag",
  "flag": "flag{example}",
  "abstention": false,
  "metadata": {}
}
```

### Categories
`web`, `crypto`, `rev`, `forensics`, `osint`, `pwning`, `misc`

### Abstention triples
10% of entries are uncertainty-injected: the solution is stripped and Zero learns
to reason about what it *cannot* determine and why. This addresses the Phase 1
finding that baseline models produce zero abstentions (confidently wrong).

## Setup

```bash
cd phase2
pip install -r requirements.txt
cp .env.example .env
# fill in .env with your credentials
```

## Running

```bash
# Full pipeline (all sources)
python run.py

# Single source, dry run (no Claude API calls, no HF push)
python run.py --sources picoctf --dry-run

# Skip HF upload (keep local only)
python run.py --no-push

# Custom limits
python run.py --max-ctftime-pages 10 --max-pico 200 --max-htb-machines 50
```

## Credentials

| Env var | Where to get it |
|---|---|
| `CTFTIME_SESSION` | devtools → Application → Cookies → ctftime.org → `sessionid` |
| `HTB_TOKEN` | Profile Settings → App Tokens → Create App Token |
| `ANTHROPIC_API_KEY` | console.anthropic.com |
| `HF_TOKEN` | huggingface.co → Settings → Access Tokens (write) |

## Output

- Local: `phase2/data/seed.jsonl`
- HF Hub: [`notvcto/zero-dataset`](https://huggingface.co/datasets/notvcto/zero-dataset)
- Split: 95% train / 5% test (held out for eval Layer 1)

## Design decisions

**Hybrid enrichment**: Raw writeups are messy. We extract structure heuristically
then use Claude to normalize into Zero's voice and fill reasoning gaps. For crypto,
the enrichment prompt explicitly requires full worked computations — addressing the
Phase 1 finding that all models hallucinated base64 outputs.

**Uncertainty injection**: 10% of entries have their solution stripped. Zero learns
both how to solve *and* how to recognize when it can't. Penalizing confident-wrong
answers is built into the GRPO reward; this gives the model training signal for
correct abstention behavior before the reward loop begins.

**zero-forge is not here**: The adversarial problem generator lives in a private
repo and is not part of this pipeline. This pipeline builds the seed corpus only.
zero-forge runs in Phase 3.
