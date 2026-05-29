"""
Enrichment layer
Produces prompts for manual enrichment via Claude Code.
No API calls — prompts are written to a batch file for human-in-the-loop processing.
"""

import json
import logging
from schema import RawEntry

log = logging.getLogger(__name__)


# ─── Prompts ──────────────────────────────────────────────────────────────────

SYSTEM_PROMPT = """You are building training data for Zero, a small language model trained to reason through security and CTF problems.

Zero's voice:
- Direct. No hedging, no filler phrases ("Great question!", "Certainly!", "As an AI...").
- Confident calibration: if the answer is known, state it. If uncertain, say exactly what's uncertain and why.
- Shows its work. Every claim is grounded in a concrete step.
- Never hallucinates flags or tools. If something wasn't in the source material, don't invent it.
- For crypto: always includes full worked computations (actual numbers, actual code), not just "then we decrypt it".

Output ONLY valid JSON. No markdown fences. No preamble."""


ENRICH_PROMPT = """\
{system}

You have a raw CTF/security writeup. Your job is to produce a clean training triple.

Source: {source}
Category: {category}
Difficulty: {difficulty}

--- RAW CHALLENGE DESCRIPTION ---
{challenge}

--- RAW REASONING STEPS (may be partial or messy) ---
{steps}

--- SOLUTION HINT ---
{solution_hint}

--- FLAG (if known) ---
{flag}

Produce a JSON object with exactly these fields:
{{
  "challenge": "Clean, self-contained problem statement. Include all info needed to solve it. 2-4 sentences.",
  "reasoning_chain": "Step-by-step reasoning as Zero would reason through it. Show every logical step. For crypto, include actual computations. For web, include actual payloads. Minimum 3 steps. Use newlines between steps.",
  "solution": "The final answer. Concise. If there's a flag, include it. If no flag, state the concrete outcome."
}}

Rules:
- Never invent flags or exploit details not present in the source material.
- If the source material is too thin to produce a complete reasoning chain, set reasoning_chain to exactly: "INSUFFICIENT_DATA"
- For crypto challenges: reasoning_chain MUST include actual numerical/code computation steps.
- Keep Zero's voice throughout: direct, grounded, no filler."""


ABSTENTION_PROMPT = """\
{system}

You have a CTF challenge description with NO solution provided.
Produce a training triple where Zero correctly identifies what it can and cannot determine.

Source: {source}
Category: {category}

--- CHALLENGE DESCRIPTION ---
{challenge}

Produce a JSON object with exactly these fields:
{{
  "challenge": "Clean, self-contained problem statement.",
  "reasoning_chain": "Zero's reasoning about the problem: what it can observe, what attack surface exists, what additional information would be needed to solve it. Be specific about the gap.",
  "solution": "State clearly what cannot be determined without [specific missing info] and what the approach would be if that info were available."
}}"""


# ─── Prompt builder ───────────────────────────────────────────────────────────

def build_prompt(entry: RawEntry, normalized: dict, abstention: bool = False) -> str:
    """Build the enrichment prompt for a single entry."""
    if abstention:
        return ABSTENTION_PROMPT.format(
            system=SYSTEM_PROMPT,
            source=entry.source,
            category=entry.category,
            challenge=normalized["challenge"][:1000],
        )
    else:
        steps_text = "\n\n".join(normalized.get("steps_raw", [])) or "(none extracted)"
        return ENRICH_PROMPT.format(
            system=SYSTEM_PROMPT,
            source=entry.source,
            category=entry.category,
            difficulty=entry.difficulty,
            challenge=normalized["challenge"][:800],
            steps=steps_text[:2000],
            solution_hint=normalized.get("solution_hint", "")[:600],
            flag=normalized.get("flag") or "unknown",
        )


def enrich(entry: RawEntry, normalized: dict, abstention: bool = False) -> dict | None:
    """
    Enrichment is handled manually via Claude Code.
    This function is a no-op pass-through: it returns a passthrough triple
    using normalized data directly, preserving structure for the batch file.

    The actual enrichment happens in two steps:
      1. run.py --scrape-only  → produces data/raw.jsonl
      2. Claude Code reads data/raw.jsonl, enriches each entry, writes data/seed.jsonl
    """
    # Pass-through: use normalized data as-is
    # Claude Code will rewrite these into proper triples
    steps_text = "\n\n".join(normalized.get("steps_raw", [])) or ""
    return {
        "challenge": normalized["challenge"],
        "reasoning_chain": steps_text or normalized.get("solution_hint", ""),
        "solution": normalized.get("solution_hint", "") or normalized.get("flag", "unknown"),
    }
