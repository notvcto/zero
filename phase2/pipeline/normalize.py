"""
Normalization layer
Extracts structured fields (challenge, steps, solution) from raw writeup text.
Prepares input for the Claude enrichment step.
"""

import re
import logging
from schema import RawEntry

log = logging.getLogger(__name__)


# ─── Heuristic extraction ─────────────────────────────────────────────────────

_SOLUTION_MARKERS = [
    r"(?i)(flag|solution|answer|the\s+flag\s+is|we\s+get\s+(?:the\s+)?flag)",
    r"(?i)(root\.txt|user\.txt|congratulations|owned|rooted)",
]

_STEP_HEADERS = re.compile(
    r"(?im)^#+\s+(.+)$|^(recon|enumeration|foothold|exploitation|privesc|privilege\s+escalation|"
    r"user|root|flags?|solution|approach|methodology)\s*[:\-]?\s*$"
)

_CODE_BLOCK = re.compile(r"```[\s\S]*?```|`[^`]+`")
_FLAG_RE = re.compile(r"(\w+CTF\{[^}]+\}|flag\{[^}]+\}|HTB\{[^}]+\})", re.IGNORECASE)


def _split_into_sections(text: str) -> list[tuple[str, str]]:
    """Split text into (heading, body) pairs by markdown headers or known keywords."""
    sections = []
    current_heading = "intro"
    current_body = []

    for line in text.splitlines():
        header_match = _STEP_HEADERS.match(line)
        if header_match:
            if current_body:
                sections.append((current_heading, "\n".join(current_body).strip()))
            current_heading = (header_match.group(1) or header_match.group(2) or line).strip().lower()
            current_body = []
        else:
            current_body.append(line)

    if current_body:
        sections.append((current_heading, "\n".join(current_body).strip()))

    return sections


def _extract_challenge_description(raw_text: str, source: str) -> str:
    """
    Extract the challenge/problem statement from raw text.
    For CTFtime/PicoCTF: usually in the first section.
    For HTB: the machine intro + objective.
    """
    lines = raw_text.splitlines()

    # PicoCTF entries are already structured as "title + description"
    if source == "picoctf":
        # First meaningful block after the header lines
        body_lines = []
        in_header = True
        for line in lines:
            if in_header and re.match(r"^(Category|Points|Hints?):", line):
                continue
            in_header = False
            body_lines.append(line)
        return "\n".join(body_lines[:30]).strip()

    # HTB: first 15 lines tend to be the machine overview
    if source in ("htb_official", "htb_community"):
        return "\n".join(lines[:20]).strip()

    # CTFtime: heuristically find the problem statement before solution steps
    sections = _split_into_sections(raw_text)
    if sections:
        # First section is usually the challenge description
        intro = sections[0][1]
        if len(intro) > 30:
            return intro[:800].strip()

    # Fallback: first 20 non-empty lines
    non_empty = [l for l in lines if l.strip()]
    return "\n".join(non_empty[:20]).strip()


def _extract_solution_hint(raw_text: str) -> str:
    """
    Extract the final solution / flag area as a rough hint for enrichment.
    Not the full solution — just the last section + any flags found.
    """
    flags = _FLAG_RE.findall(raw_text)

    sections = _split_into_sections(raw_text)
    solution_sections = []
    for heading, body in sections:
        if any(re.search(marker, heading) for marker in _SOLUTION_MARKERS):
            solution_sections.append(body)

    if solution_sections:
        combined = "\n\n".join(solution_sections)
        if flags:
            combined += f"\n\nFlag: {flags[-1]}"
        return combined[:1000].strip()

    # Fallback: last 20 non-empty lines
    non_empty = [l for l in raw_text.splitlines() if l.strip()]
    tail = "\n".join(non_empty[-20:]).strip()
    if flags:
        tail += f"\n\nFlag: {flags[-1]}"
    return tail[:1000].strip()


def _extract_steps(raw_text: str) -> list[str]:
    """Extract the intermediate reasoning steps from a writeup."""
    sections = _split_into_sections(raw_text)

    # Skip intro and solution — everything in between is reasoning
    skip_headings = {"intro", "challenge", "tl;dr", "tldr"}
    solution_headings = {"flag", "flags", "solution", "root", "user", "answer"}

    steps = []
    for heading, body in sections:
        h = heading.lower()
        if h in skip_headings:
            continue
        if any(sol in h for sol in solution_headings) and len(steps) > 0:
            break  # stop at solution section
        if body.strip():
            steps.append(f"[{heading}]\n{body.strip()}")

    return steps


def normalize(entry: RawEntry) -> dict:
    """
    Convert a RawEntry into a normalized dict ready for Claude enrichment.
    Returns:
        {
          challenge: str,
          steps_raw: list[str],
          solution_hint: str,
          flag: str | None,
        }
    """
    raw = entry.raw_text

    challenge = _extract_challenge_description(raw, entry.source)
    steps = _extract_steps(raw)
    solution_hint = _extract_solution_hint(raw)

    flag = entry.flag
    if not flag:
        flags_found = _FLAG_RE.findall(raw)
        flag = flags_found[-1] if flags_found else None

    return {
        "challenge": challenge,
        "steps_raw": steps,
        "solution_hint": solution_hint,
        "flag": flag,
    }


if __name__ == "__main__":
    from schema import RawEntry
    sample = RawEntry(
        source="ctftime",
        title="Simple SQLi",
        url="http://example.com",
        raw_text="""# Simple SQLi

## Challenge
Login as admin without knowing the password.
URL: http://example.com/login

## Enumeration
Tried basic ' OR '1'='1 on username field. Got an error.

## Exploitation
Used: admin'--
Password: anything

## Flag
flag{sql_injection_is_fun}
""",
        category="web",
    )
    result = normalize(sample)
    print("Challenge:", result["challenge"][:200])
    print("Steps:", result["steps_raw"])
    print("Flag:", result["flag"])
