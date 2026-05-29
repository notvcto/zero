"""
Uncertainty injection
Randomly selects ~10% of entries and strips their solution,
forcing the model to learn calibrated abstention.
"""

import random
import logging
from schema import RawEntry

log = logging.getLogger(__name__)

INJECTION_RATE = 0.10  # 10% of entries become abstention triples


def should_inject(seed: str, rate: float = INJECTION_RATE) -> bool:
    """Deterministic decision based on entry id — same entry always gets same treatment."""
    h = hash(seed) % 1000
    return h < int(rate * 1000)


def strip_solution(normalized: dict) -> dict:
    """
    Return a copy of normalized with solution_hint and flag removed.
    The challenge description is preserved but steps are removed too,
    since they often contain the solution.
    """
    return {
        "challenge": normalized["challenge"],
        "steps_raw": [],
        "solution_hint": "",
        "flag": None,
    }


def inject(entry: RawEntry, normalized: dict) -> tuple[dict, bool]:
    """
    Decide whether to inject uncertainty for this entry.
    Returns (normalized_dict, is_abstention).
    If abstention: solution is stripped, enrich() will use abstention prompt.
    """
    if should_inject(f"{entry.source}:{entry.title}:{entry.url}"):
        log.info(f"  ↩ uncertainty injection: {entry.title[:50]}")
        return strip_solution(normalized), True
    return normalized, False
