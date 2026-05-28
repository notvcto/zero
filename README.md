# zero

> A small reasoning model trained on security problems. No hedging. No sugar coating.

**[Read the announcement →](https://notvc.to/blog/zero-announcement)**

---

Zero is an open-source family of small language models trained on CTF challenges
via adversarial self-play with GRPO. Security is the training domain — chosen because
CTF problems have verifiable answers, clean reasoning chains, and no room to
pattern-match your way to a solution. The research question is whether rigorous
training on that domain produces a model that reasons well in general.

The directness is baked into the reward function, not prompted in. Calibrated
uncertainty is rewarded. Confident wrong answers are penalized hardest.

---

## Model family

| Model       | Status  | Notes           |
| ----------- | ------- | --------------- |
| `zero-1.5b` | Planned | MVR lower bound |
| `zero-3b`   | Planned | Primary release |
| `zero-7b`   | Planned | MVR upper bound |

---

## Spec

The full design is in **[SPEC.md](SPEC.md)** — training architecture, reward function
implementation, self-play failure mode mitigations, evaluation framework, dataset strategy.

---

## Status

**Phase 2 — Dataset construction.** Phase 1 baseline evaluation is complete. All three
model sizes scored ~25% with no training. Scaling did nothing — the capability gap is in
training signal, not base weights. Phase 2 is now underway: building the seed dataset from
real CTF writeups, normalized into Zero's voice register.

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
