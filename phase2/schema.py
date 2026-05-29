"""
Zero Dataset Schema
Triple format: (challenge, reasoning_chain, solution)
"""

from dataclasses import dataclass, field, asdict
from typing import Optional
from enum import Enum
import hashlib
import json


class Category(str, Enum):
    WEB = "web"
    CRYPTO = "crypto"
    REV = "rev"
    FORENSICS = "forensics"
    OSINT = "osint"
    PWNING = "pwning"
    MISC = "misc"
    UNKNOWN = "unknown"


class Source(str, Enum):
    CTFTIME = "ctftime"
    PICOCTF = "picoctf"
    HTB_OFFICIAL = "htb_official"
    HTB_COMMUNITY = "htb_community"


class Difficulty(str, Enum):
    EASY = "easy"
    MEDIUM = "medium"
    HARD = "hard"
    INSANE = "insane"
    UNKNOWN = "unknown"


@dataclass
class RawEntry:
    """Raw scraped entry before normalization."""
    source: str
    title: str
    url: str
    raw_text: str
    category: str = "unknown"
    difficulty: str = "unknown"
    flag: Optional[str] = None
    metadata: dict = field(default_factory=dict)


@dataclass
class Triple:
    """
    A Zero training triple.
    challenge     — the problem statement as presented to the model
    reasoning_chain — step-by-step reasoning toward the solution
    solution      — the final answer / flag / explanation
    """
    id: str
    source: str
    category: str
    difficulty: str
    challenge: str
    reasoning_chain: str
    solution: str
    flag: Optional[str] = None
    abstention: bool = False   # True if reasoning_chain was stripped (uncertainty injection)
    metadata: dict = field(default_factory=dict)

    @classmethod
    def make_id(cls, source: str, title: str, url: str) -> str:
        raw = f"{source}:{title}:{url}"
        return hashlib.sha256(raw.encode()).hexdigest()[:16]

    def to_jsonl(self) -> str:
        return json.dumps(asdict(self), ensure_ascii=False)

    def validate(self) -> list[str]:
        errors = []
        if not self.challenge or len(self.challenge.strip()) < 20:
            errors.append("challenge too short")
        if not self.abstention:
            if not self.reasoning_chain or len(self.reasoning_chain.strip()) < 50:
                errors.append("reasoning_chain too short")
        if not self.solution or len(self.solution.strip()) < 5:
            errors.append("solution too short")
        if self.source not in [s.value for s in Source]:
            errors.append(f"unknown source: {self.source}")
        return errors
