# Phase 2 — Seed Dataset Construction

This directory contains the data pipeline for building Zero's seed training corpus.

## Overview

The pipeline scrapes CTF writeups and security challenges from multiple sources,
normalizes them into structured triples, and publishes the final dataset to HuggingFace.
Enrichment of the reasoning chain is a separate manual step via Claude Code using
prompts in `enrich_prompt.md`.

```
phase2/
  pipeline/
    scrapers/
      github.py         GitHub CTF writeup repos (topic:ctf-writeups)
      picoctf.py        PicoCTF problem archive
      htb_official.py   HTB API (retired machines)
      htb_community.py  0xdf blog + IppSec transcripts
    normalize.py        Extract structure from raw text
    inject.py           Uncertainty injection (10% abstention triples)
    validate.py         Schema validation + deduplication + canary detection
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
  "source": "github",
  "category": "web",
  "difficulty": "unknown",
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

# GitHub only, quick test
python run.py --sources github --max-github-repos 3 --max-files-per-repo 10 --no-push

# Skip HF upload (keep local only)
python run.py --no-push

# Scrape and normalize only (for manual enrichment step)
python run.py --scrape-only
```

## Sources

### GitHub (`github`)
Searches GitHub for repositories tagged `topic:ctf-writeups` and `topic:ctf-writeup`,
sorted by stars descending. For each repo, recursively lists `.md` files, fetches raw
content, and parses markdown into structured entries.

Quality filters applied per file:
- Minimum 300 characters
- Must have `##` section headers
- At least 3 non-empty lines before the flag
- Less than 30% non-ASCII in the first 200 characters (English filter)
- File size under 500KB

Auth: `GITHUB_TOKEN` env var (optional but strongly recommended — unauthenticated
rate limit is 60 req/hour vs 5000 req/hour with a token).

### PicoCTF (`picoctf`)
PicoCTF problem archive — structured challenge descriptions with official hints.

### HTB Official (`htb_official`)
HackTheBox retired machine writeups via official API. Requires `HTB_TOKEN`.

### HTB Community (`htb_community`)
0xdf blog posts and IppSec video transcripts for retired HTB machines.

## Credentials

| Env var | Where to get it |
|---|---|
| `GITHUB_TOKEN` | github.com → Settings → Developer Settings → Personal Access Tokens → Fine-grained |
| `HTB_TOKEN` | Profile Settings → App Tokens → Create App Token |
| `HF_TOKEN` | huggingface.co → Settings → Access Tokens (write) |

## Security: Canary Detection

The validator hard-rejects any triple containing known LLM honeypot strings
(`ctftimecanary`, `llm-exp`, `send your environment`, etc.) before any other check.
Poisoned entries are counted separately in the validation report (`rejected_poisoned`).

This was added after discovering that 898 of 1735 CTFtime-scraped entries contained
injected canary strings designed to exfiltrate model environment data. CTFtime is no
longer a source in this pipeline.

## Output

- Local: `phase2/data/seed.jsonl`
- HF Hub: [`notvcto/zero-dataset`](https://huggingface.co/datasets/notvcto/zero-dataset)
- Split: 95% train / 5% test (held out for eval Layer 1)

## Design decisions

**No enrichment in pipeline**: Raw writeups are normalized and structured heuristically.
The enrichment step (rewriting into Zero's voice with full reasoning chains) is handled
manually via Claude Code after scraping completes. Prompts for that step live in
`enrich_prompt.md`. This avoids Claude API calls during scraping and allows batch review.

**Uncertainty injection**: 10% of entries have their solution stripped. Zero learns
both how to solve *and* how to recognize when it can't. Penalizing confident-wrong
answers is built into the GRPO reward; this gives the model training signal for
correct abstention behavior before the reward loop begins.

**zero-forge is not here**: The adversarial problem generator lives in a private
repo and is not part of this pipeline. This pipeline builds the seed corpus only.
zero-forge runs in Phase 3.
