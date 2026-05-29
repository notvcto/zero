"""
Validation + deduplication layer
Validates triples against schema and deduplicates by content hash.
"""

import hashlib
import logging
from schema import Triple

log = logging.getLogger(__name__)


def content_hash(triple: Triple) -> str:
    """Hash on challenge text to catch near-duplicates."""
    normalized = triple.challenge.lower().strip()
    return hashlib.md5(normalized.encode()).hexdigest()


class Validator:
    def __init__(self):
        self._seen_hashes: set[str] = set()
        self._seen_ids: set[str] = set()
        self.stats = {
            "accepted": 0,
            "rejected_validation": 0,
            "rejected_duplicate": 0,
        }

    def accept(self, triple: Triple) -> bool:
        """Return True if triple passes validation and deduplication."""
        # Schema validation
        errors = triple.validate()
        if errors:
            log.debug(f"  ✗ validation failed [{', '.join(errors)}]: {triple.id}")
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
            f"{self.stats['rejected_validation']} invalid, "
            f"{self.stats['rejected_duplicate']} duplicate"
        )
