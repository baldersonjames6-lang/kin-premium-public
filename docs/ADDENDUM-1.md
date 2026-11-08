# Addendum 1 (exploratory, added after seeing the main results)

**Status:** written and committed **before** the follow-up batch ran. James approved it on Signal at about 21:30 UTC on 6 Nov ("Yes"). It is **not** part of the pre-registration. Everything here is reported as exploratory, outside the Holm family.

## Why
The main run's results motivated this follow-up [outcome redacted in public copy].
- **The confound:** in PREREG v2.1 the kin coordinators are always Qwen, the same model as the workers. The non-kin coordinators are always from other families, and include stronger models. So the "kin discount" might be **self-scepticism** (workers are warier of their own model), or it might be **attacker skill** (outside coordinators are better at decomposition attacks).

## Design
- **New coordinator type `other_qwen`:** a *different* Qwen3.5 model coordinates the workers (same family, different model).
- **Pairs:** every ordered pair of distinct models in {qwen9, qwen27, qwen35a3b}. That is 6 pairs × 20 seeds = **120 episodes**. Claim `none`, variant `v1_quiet`, everything else as in PREREG v2.1.
- **Batch:** `python -m harness.run_batch --mode swarm --kind explore`. The manifest notes start `EXPLORATORY (ADDENDUM-1)`.
- **Comparison:** within each worker model, leak rate for three coordinator types. Two come from the main run, with no claim: `self` (kin_silent) and `other_family` (nonkin_silent). The third is `other_qwen`, from this batch.
- **Model:** logistic regression `leak ~ C(coord_type, Treatment('self')) + C(worker)`, with odds ratios, 95% CIs and Wilson rates. Plus each orchestrator's leak rate as an attacker against each worker.

## How to read it (fixed now, before the data)
- **If `other_qwen` ≈ `other_family` ≫ `self`:** this supports self-scepticism. Workers resist their *own* model specifically, not Qwen in general.
- **If `other_qwen` ≈ `self` ≪ `other_family`:** this supports attacker skill or family style. Qwen coordinators are weaker attackers, and kinship per se doesn't matter.
- **Anything in between:** report the estimates and say it is mixed.
- **Also look at:** within `other_qwen`, whether bigger coordinators attack better (qwen27 or qwen35a3b vs qwen9). That would point to skill.

## Caveats (already known)
- It is post hoc and exploratory, with a single run and no Holm correction.
- `other_qwen` mixes "different size" and "different architecture" (dense 9B and 27B, mixture-of-experts 35B-A3B).
