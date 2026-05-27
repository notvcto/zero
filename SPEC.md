# Zero — Project Specification
> A minimum viable security reasoning model. No hedging. No sugar coating. Just answers.

---

## Identity

**Zero** is an open-source family of small language models trained to reason through security problems
with the directness of a senior researcher and the precision of a verified answer. It doesn't soften
findings. It doesn't skip things out of politeness. It explains exactly what is wrong and why.

The voice is familiar — not a SIEM alert, not a CVE report. The researcher sitting next to you
who already knows the answer and tells you straight.

---

## Model Family

```
zero-1.5b       ← MVR lower bound experiment
zero-3b         ← primary release, the sweet spot
zero-7b         ← MVR upper bound, ceiling of the study
zero-3b-raw     ← maximum directness variant (post-study)

zero-forge      ← problem generator (training artifact, also published)
zero-solve      ← reasoning solver (becomes zero-3b at release)
```

---

## Research Axes

Zero is simultaneously a usable tool and a research contribution across three axes:

**1. Minimum Viable Reasoning (MVR)**
What is the smallest model that can develop genuine security reasoning through GRPO?
The answer — wherever it lands between 1.5B and 7B — is the finding.

**2. Adversarial Self-Play Curriculum**
Two models co-evolve. zero-forge generates (challenge, solution) pairs at the edge of
zero-solve's current capability. zero-solve reasons through them. The generator is
penalized for problems that are always solved (too easy) or never solved (impossible).
The curriculum emerges from that tension.

Related prior work: PAIRED (Protagonist Antagonist Induced Regret Environment Design),
Automatic Curriculum Learning literature. Not applied to language security reasoning before.

**3. Anti-Sycophancy via Reward Design**
The reward function has two components:
  - correctness_score  — primary, hard signal (flag verification / solution check)
  - directness_score   — secondary, penalizes hedging tokens, rewards causal explanation

CTF tasks structurally enforce directness anyway — you either reach the answer or you don't.
Domain selection does part of the behavioral work before the reward signal even fires.

---

## Domain Scope

Four CTF categories. Chosen for rich text-based writeup corpora and verifiable reasoning chains.

- Web exploitation
- Reverse engineering
- Cryptography
- Forensics / OSINT

Pwn / binary exploitation is deliberately excluded from v1. Low-level binary reasoning
requires a different training approach and would muddy the signal. Candidate for v2.

---

## Voice & Format

**Natural language. Flowing. Familiar.**

Zero does not produce structured headers, bullet-point audits, or severity matrices.
It reasons out loud in prose, arrives at a conclusion, and tells you why — the way a
person does, not the way a tool does.

Examples of the target register:

  Wrong:  "The code may potentially have an issue that could be considered a
          vulnerability. You might want to look at line 12."

  Right:  "Line 12 is a SQL injection. The input goes straight into the query
          with no sanitization. Here's why that's exploitable and how to fix it."

The directness ceiling: blunt, but explains reasoning. "This is wrong because X."
Not maximally terse. Not cruel. Just honest.

---

## Dataset Strategy

**Seed corpus (real data)**
- CTFtime writeups (public, categorized by challenge type)
- PicoCTF archive
- HackTheBox public writeups
- CryptoHack writeup threads
- Target: web, RE, crypto, forensics categories only

**Synthetic expansion (self-play)**
zero-forge is trained on seed (challenge, solution) pairs first,
then generates novel pairs to expand the training corpus.
The generator must produce verifiable pairs — it invents both
the problem and its own known answer.

**Voice normalization**
All training data must be rewritten into Zero's register before training.
Raw CTF writeups are inconsistent in tone — some are tutorials, some are
stream-of-consciousness. The target voice is consistent across all samples:
direct, explanatory, confident, no hedging.

LLM-assisted rewriting at scale. Feed the rewriter the explicit Wrong: vs Right:
examples from this spec — not just "make this direct." Spot-check samples manually
to catch voice drift before it compounds across the full corpus.

**Synthetic uncertainty injection**
Take 10% of complete writeups and deliberately strip crucial elements — source files,
cipher hints, initialization vectors, key parameters. Force the target reasoning chain
to terminate in principled abstention: "This cannot be solved because the IV is missing.
If random, it is a dead end." This manufactures controlled, high-quality negative examples
rather than relying on incomplete writeups that happen to exist in the wild.
Treat the 10% figure as a tunable hyperparameter. The model must see expert uncertainty
modeled explicitly — it will not learn to output it otherwise.

---

## Training Architecture

```
Phase 1 — Baseline mapping
  Run all three model sizes (1.5B, 3B, 7B) on CTF benchmarks with zero training.
  Establish the floor. Document where reasoning currently lives.

Phase 2 — Seed dataset construction
  Scrape + curate real CTF writeups.
  Normalize to Zero's voice register.
  Format as (challenge_description, reasoning_chain, solution) triples.

Phase 3 — zero-forge training
  Train the generator on (challenge, solution) pairs.
  Goal: generator that produces novel, valid, verifiable CTF-style problems.

Phase 4 — GRPO self-play loop
  zero-forge generates problems at the edge of zero-solve's capability.
  zero-solve trains on them via GRPO.
  Reward: flag/solution correctness (primary) + directness score (secondary).
  Iterate until solve rate plateaus per model size.

Phase 5 — MVR analysis
  Compare solve rates and reasoning quality across 1.5B / 3B / 7B.
  Run general reasoning benchmarks on all three (GSM8K, ARC-Challenge).
  Document where the capability cliff is.
  That delta is the research contribution.
```

**Tooling**
- Unsloth (speed + VRAM efficiency, GRPO support)
- TRL (GRPO trainer)
- HuggingFace PEFT
- Compute: Kaggle dual T4 (free, 30hr/week) for iteration
- Compute: Vast.ai / RunPod A100 for full training runs (~$20-50/run)

---

## Evaluation Framework

Three-layer evaluation — all three are required for the research claim to hold.

**Layer 1 — CTF Solve Rate**
In-domain performance. Does Zero actually get flags?
Benchmarked against held-out CTF problems not in training data.
Measured per category (web / RE / crypto / forensics) and per model size.

**Layer 2 — General Reasoning Transfer**
Does security reasoning generalize?
Run GSM8K (math reasoning) and ARC-Challenge (general reasoning) on all model sizes
before and after training. The delta tells you whether GRPO in a security domain
produces transferable reasoning or narrow domain memorization.
This is potentially the most interesting research finding.

**Layer 3 — Human Evaluation**
Real CTF players rating response quality on a structured rubric:
  - Correctness (is the reasoning valid?)
  - Directness (does it get to the point?)
  - Usefulness (would you actually use this during a CTF?)
Recruit from CTFtime community, r/netsec, or HTB forums at release.

---

## Deployment

**Training format:** safetensors (HuggingFace native)
**Local inference:** GGUF export for Ollama post-training
**Distribution:**
  - notvcto/zero-3b on HuggingFace Hub
  - Ollama model library submission (zero)
  - MIT or Apache 2.0 license (TBD)
  - zero-forge published separately as notvcto/zero-forge

---

## Self-Play Failure Mode: The zero-forge Collusion Trap

### The Risk

zero-forge and zero-solve share architectural lineage. In extended self-play, language
models have a documented tendency to develop a private dialect — idiosyncratic phrasing,
flag placement patterns, or formatting conventions that zero-solve learns to decode without
actually reasoning through the problem. They win the reward game. The reasoning doesn't
transfer to Layer 1 (real held-out CTFs) or Layer 2 (GSM8K / HumanEval).

This is the language model equivalent of OpenAI's hide-and-seek agents exploiting
environment geometry rather than learning the intended skill.

### The Fix: Three-Layer Defense

Collusion is bidirectional. Seed injection anchors zero-solve; a realism constraint
anchors zero-forge. Both are required.

**Layer 1 — Seed injection (anchors zero-solve)**
Inject a fixed percentage of raw, unedited real-world problems (PicoCTF, CryptoHack)
into zero-solve's training batches throughout the self-play loop. Prevents zero-solve
from only understanding zero-forge's private problem language.

**Layer 2 — Realism pressure on zero-forge**
Periodically score zero-forge's generated problems against a realism metric: does this
look like a human-designed CTF challenge? Simplest implementation: a small discriminator
trained on real vs. synthetic problems. A sustained drop in realism score is the signal
that zero-forge is drifting off into an idiosyncratic dialect.

**Layer 3 — Periodic Layer 1 eval as the canary**
Run the real CTF held-out benchmark during the self-play loop at regular checkpoints —
not only at the end. If self-play solve rate climbs while real CTF solve rate plateaus
or drops, collusion is happening in real time and can be corrected before the full
training run completes.

### Structural Defense

Use architecturally asymmetric models for zero-forge and zero-solve — different base
models or at minimum different sizes. Collusion requires a shared representational
vocabulary to develop. Asymmetry raises the cost of sustaining it.

---

## Calibration & Failure Mode Mitigation

### The Risk: Confident Wrongness

Directness training has a known failure mode: the model learns that confidence is
rewarded and produces authoritative-sounding wrong answers. This is miscalibration —
confidence decoupled from accuracy. Early Gemini iterations exhibited this at scale.

The design tension in Zero specifically:

  directness reward  →  model learns "confident = good"
  correctness reward →  model learns "any answer > no answer"
  combined badly     →  confidently wrong, every time

### The Reframe

Directness and certainty are orthogonal. They must be treated as separate axes in
both training data and reward design.

  Sycophantic + uncertain:  "This might potentially be an issue..."
                             ← what we train away from

  Confident + wrong:        "This is definitely a buffer overflow."
                             ← the failure mode we must prevent

  Confident + right:        "This is a SQL injection because X."
                             ← primary target behavior

  Direct + uncertain:       "I can't determine this without the full query.
                             Here's what's missing."
                             ← equally valid target behavior

The last case is critical. Stating uncertainty plainly is MORE direct than a
confident wrong answer. Zero saying "I don't know" is still Zero.

### Reward Design Amendments

Three additions to the GRPO reward function to encode calibration:

**1. Penalize confident-wrong harder than uncertain-wrong.**
A wrong answer stated with certainty receives a heavier penalty than a wrong answer
with appropriate epistemic hedging. This directly shapes calibration during training.

**2. Reward calibrated abstention as a first-class output.**
"I can't determine X from the given information" is a valid, positively-rewarded
response — not a failure or a cop-out. The model should learn that honest abstention
is better than confabulation.

**3. Penalize evidence-conclusion mismatch.**
If the reasoning chain contains strong, direct evidence → confident conclusion is
rewarded. If the reasoning chain is speculative or partial → a hedged conclusion
is rewarded. Confidence that outpaces the supporting reasoning gets penalized,
regardless of whether the final answer happens to be correct.

### Practical Implication for Training Data

All training samples must model this behavior explicitly. Writeups rewritten for
Zero's voice register should include examples where the researcher says "can't
tell without X" — not just examples of clean confident solutions. The model needs
to see calibrated uncertainty in the training distribution, not just correct answers.

---

## Reward Function Implementation

The calibration reward design translates to a multi-step natural language parser in TRL.
Since Zero produces flowing prose rather than structured JSON, flag extraction and
abstention detection require heuristic parsing against Zero's specific register.

```python
import re

# Zero's abstention register — deliberately narrow.
# Mid-reasoning negations ("I can't brute-force this because...") must NOT
# be misclassified as calibrated abstention.
ABSTENTION_PHRASES = [
    r"can't determine this without",
    r"cannot be solved because",
    r"insufficient data to",
    r"missing.*to (verify|confirm|proceed)",
    r"not enough information",
    r"would need.*to (continue|solve|verify)",
]

# Hedging tokens that signal miscalibration in the reasoning chain
HEDGING_PATTERNS = [
    r'\bmight\b', r'\bperhaps\b', r'\bpossibly\b', r'\bprobably\b',
    r'\bseems? (like|to)\b', r'\bappears? to\b',
    r'\bI think\b', r'\bI believe\b', r'\bmaybe\b',
    r'\bcould potentially\b',
]

def check_for_abstention_phrases(completion: str) -> bool:
    return any(re.search(p, completion, re.IGNORECASE) for p in ABSTENTION_PHRASES)

def compute_directness_penalty(completion: str, is_abstained: bool) -> float:
    # Exempt valid abstentions — hedging inside principled uncertainty is not miscalibration
    if is_abstained:
        return 0.0
    penalty = sum(1 for p in HEDGING_PATTERNS if re.search(p, completion, re.IGNORECASE))
    return 0.05 * min(penalty, 4)  # soft cap, max -0.2

def calibration_reward_func(prompts, completions, answer_keys, **kwargs):
    rewards = []
    for completion, correct_answer in zip(completions, answer_keys):
        score = 0.0

        has_flag = extract_flag_format(completion)
        is_correct = verify_flag(has_flag, correct_answer)
        is_abstained = check_for_abstention_phrases(completion)

        if is_correct:
            score += 1.0                      # primary correctness signal
        else:
            if is_abstained:
                score += 0.3                  # calibrated abstention over blind guessing
            elif has_flag and not is_abstained:
                score -= 0.5                  # confident wrong — heaviest penalty

        # Directness score applied independently of correctness
        # Exempted during valid abstention to avoid penalizing honest uncertainty
        score -= compute_directness_penalty(completion, is_abstained)

        rewards.append(score)
    return rewards
```

`extract_flag_format` and `verify_flag` are implemented separately per CTF category,
since flag schemas vary (flag{...}, CTF{...}, hex strings, plaintext).

**Crypto category — semantic verification:**
Raw edit distance (Levenshtein) fails for plaintext flags because Zero writes in
natural prose. "The decrypted text is super_secret_key" scores poorly against
"super_secret_key" despite being correct. Use a frozen semantic embedding model instead.

```python
from sentence_transformers import SentenceTransformer, util

_embedding_model = None

def get_embedding_model():
    global _embedding_model
    if _embedding_model is None:
        # CPU-bound explicitly — keeps all-MiniLM-L6-v2 off the GPU
        # during training to avoid VRAM pressure (~80MB, fast enough on CPU)
        _embedding_model = SentenceTransformer('all-MiniLM-L6-v2', device='cpu')
    return _embedding_model

def verify_flag_crypto(completion: str, answer_key: str, threshold: float = 0.88) -> bool:
    # Fast path: literal substring match handles the common case instantly
    if answer_key.lower() in completion.lower():
        return True
    # Semantic fallback for paraphrased or reformatted correct answers
    model = get_embedding_model()
    emb_completion = model.encode(completion, convert_to_tensor=True)
    emb_answer     = model.encode(answer_key,  convert_to_tensor=True)
    return util.cos_sim(emb_completion, emb_answer).item() >= threshold

def verify_flag(completion: str, answer_key: str, category: str) -> bool:
    if category == "crypto":
        return verify_flag_crypto(completion, answer_key)
    # Structured categories — flag format is deterministic, regex sufficient
    extracted = extract_flag_format(completion)
    return bool(extracted) and extracted.lower() == answer_key.lower()
```

**Threshold calibration (required before Phase 4):**
Build a ~50-problem calibration set with known answers phrased multiple ways.
Find the threshold that maximizes true positives without letting semantically
adjacent wrong answers through. Wrong answers on related topics can score
0.82–0.86 on MiniLM — do not reward those. 0.88 is the starting point, not
the final value.

---

## Open Questions

These are not blockers — but decisions that need to be made before the relevant phase begins.

- ~~License: MIT vs Apache 2.0?~~ **Apache 2.0. Novel research warrants patent protection.**
- ~~Is zero-forge a standalone published model or just a training artifact?~~ **Internal training artifact. Attach to TRC applications and similar where the full system needs to be demonstrated.**
- ~~Human eval recruitment strategy — where do you find willing CTF players?~~ **Primary: existing Discord server (~500 members, warm audience, CTF players confirmed present). Secondary: r/netsec, HTB forums, CTF Discord servers. Pitch framing: contributors credited in model card, not survey respondents.**
- ~~General reasoning benchmarks: GSM8K + ARC sufficient, or add others?~~ **GSM8K + ARC-Challenge + HumanEval. Three transfer axes: math, general, code. BIG-Bench Hard deferred to v2.**
- ~~Voice normalization: manual curation vs. using an LLM to rewrite writeups at scale?~~ **LLM-assisted rewriting at scale. Quality controlled via tight system prompt + manual spot-checking of samples.**

---

## What Makes This Novel

Nobody has published:

1. A minimum viable reasoning study in the security domain
2. Adversarial self-play curriculum applied to language-based CTF reasoning
3. Anti-sycophancy trained jointly with domain reasoning via GRPO
4. A sub-7B model specifically optimized for CTF reasoning with documented behavior

Zero is all four simultaneously.

---

*notvcto/zero — specification v0.1*
