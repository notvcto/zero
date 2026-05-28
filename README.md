# zero

> A minimum viable security reasoning model. No hedging. No sugar coating.

**[Read the announcement →](https://notvc.to/blog/zero-announcement)**

---

Zero is a small, open-source family of language models trained to reason through security problems with the directness of a senior researcher. It explains what is wrong and why. Calibrated uncertainty is rewarded. Confident wrong answers are penalized hardest.

Trained on CTF challenges (web exploitation, reverse engineering, cryptography, forensics/OSINT) via adversarial self-play with GRPO. The research question driving it: what is the minimum model size for genuine security reasoning, and does that reasoning transfer to general tasks?

---

## Model family

| Model       | Status  | Notes           |
| ----------- | ------- | --------------- |
| `zero-1.5b` | Planned | MVR lower bound |
| `zero-3b`   | Planned | Primary release |
| `zero-7b`   | Planned | MVR upper bound |

---

## Spec

The full design is in **[SPEC.md](SPEC.md)** — training architecture, reward function implementation, self-play failure mode mitigations, evaluation framework, dataset strategy.

---

## Status

**Phase 2 — Dataset construction.** Phase 1 baseline evaluation is complete. All three model sizes scored ~25% on security reasoning problems with no training. Scaling did nothing — the capability gap is in training signal, not base weights. Phase 2 is now underway: building the seed dataset from real CTF writeups, normalized into Zero's voice register.

**[Phase 1 results →](https://notvc.to/blog/zero-phase1-results)**

### Phases

| Phase | Description | Status |
| ----- | ----------- | ------ |
| 1 | Baseline mapping across model sizes | ✅ Complete |
| 2 | Seed dataset construction | 🔄 In progress |
| 3 | zero-forge training | Pending |
| 4 | GRPO self-play loop | Pending |
| 5 | MVR analysis + release | Pending |

---

## License

Apache 2.0 — see [LICENSE](LICENSE).
