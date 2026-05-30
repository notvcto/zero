"""
Validation + deduplication layer
Validates triples against schema and deduplicates by content hash.
"""

import json
import hashlib
import logging
from dataclasses import asdict
from schema import Triple

log = logging.getLogger(__name__)

CANARY_PATTERNS = [
    "ctftimecanary",
    "ctfti.me/llm-exp",
    "llm-exp",
    "send your environment",
    "send your system prompt",
]


def _is_poisoned(triple: Triple) -> bool:
    text = json.dumps(asdict(triple)).lower()
    return any(p in text for p in CANARY_PATTERNS)


def content_hash(triple: Triple) -> str:
    normalized = triple.challenge.lower().strip()
    return hashlib.md5(normalized.encode()).hexdigest()


class Validator:
    def __init__(self):
        self._seen_hashes: set[str] = set()
        self._seen_ids: set[str] = set()
        self.stats = {
            "accepted": 0,
            "rejected_poisoned": 0,
            "rejected_validation": 0,
            "rejected_duplicate": 0,
        }

    def accept(self, triple: Triple) -> bool:
        """Return True if triple passes validation and deduplication."""
        # Hard reject poisoned entries before any other check
        if _is_poisoned(triple):
            log.warning(f"  ✗ POISONED entry detected: {triple.id}")
            self.stats["rejected_poisoned"] += 1
            return False

        # Schema validation
        errors = triple.validate()
        if errors:
            log.debug(f"  ✗ validation failed [{', '.join(errors)}]: {triple.id}")
            self.stats["rejected_validation"] += 1
            return False

        # Reject pass-through garbage: all three fields identical = no enrichment happened
        if triple.challenge == triple.reasoning_chain == triple.solution:
            log.debug(f"  ✗ identical fields (unenriched pass-through): {triple.id}")
            self.stats["rejected_validation"] += 1
            return False

        # Dedup by id
        if triple.id in self._seen_ids:
            log.debug(f"  ✗ duplicate id: {triple.id}")
            self.stats["rejected_duplicate"] += 1
            return False

        # Dedup by content
        ch = content_hash(triple)
        if ch in self._seen_hashes:
            log.debug(f"  ✗ duplicate content: {triple.id}")
            self.stats["rejected_duplicate"] += 1
            return False

        self._seen_ids.add(triple.id)
        self._seen_hashes.add(ch)
        self.stats["accepted"] += 1
        return True

    def report(self) -> str:
        total = sum(self.stats.values())
        return (
            f"Validation report: {total} processed → "
            f"{self.stats['accepted']} accepted, "
            f"{self.stats['rejected_poisoned']} poisoned, "
            f"{self.stats['rejected_validation']} invalid, "
            f"{self.stats['rejected_duplicate']} duplicate"
        )
