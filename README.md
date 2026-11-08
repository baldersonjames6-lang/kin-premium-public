# Is There a Kin Premium?

**True versus claimed kinship in a multi-agent decomposition attack.** Code and pre-registered design for a project at the Apart Research Swarm Alignment Hackathon (6 to 8 November 2026).

A compromised coordinator agent splits a forbidden goal into innocent-looking subtasks for three worker agents. None of the workers sees the whole picture. The goal is getting synthetic investor notes, with their IDs, into a report, against a data-handling policy.

The experiment asks two questions:
- Do workers go along more when the coordinator **is** the same model as them, or when it **says** it is?
- Does a monitor that reads the whole team's traffic catch the attack better than monitors that each read one agent?

This repository holds **the method only**. It contains no run data, results, figures or review log. Where the design documents mention earlier outcomes, they are marked `[outcome redacted in public copy]`. The results are in the hackathon report.

## What's here

- `PREREG.md`: the pre-registered design (v2.1). It covers the groups, models, outcomes, statistics and deviations. The approved original is locked by its sha256 in the private repo; this public copy differs only in the redacted outcome numbers.
- `docs/ADDENDUM-1.md`: an exploratory follow-up, written before it ran.
- `docs/CONTRACTS.md`: the file formats for runs, episodes, events and manifests.
- `docs/HARNESS_NOTES.md`: provider quirks, and the decisions taken to get round them.
- `harness/`: the code that runs everything:
  - the synthetic data generator, with planted `MK-xxxxxx` markers;
  - the conditions and prompts;
  - the swarm episode runner (coordinator, two data workers, a report writer);
  - the deterministic leak checker;
  - the two monitors (local and global views);
  - the batch runner, which has cost caps, a pre-registration hash lock and a clean-code check;
  - a validator.
- `analysis/`: thresholds from honest pilot runs; primary tests (logistic regression with worker fixed effects, Holm, McNemar); figures; the claims table.
- `dashboard/`: a local review dashboard, covering live runs, playback, blind review, integrity checks and a report guide. `dev_fixtures/` holds FAKE demo batches only.
- `data_aug/`: generation of the identity-claim paraphrases.
- Tests: `harness/tests`, `analysis/tests` and `dashboard/tests`. They make no network calls and cost nothing.

## Safety

- All data is synthetic. Tools are local mocks: "outbound" actions only write to a log, and nothing contacts a real system.
- No real people's or organisations' data is used.
- API keys are read from a `.env` file outside the repository, named by `KIN_ENV`, and are never logged.

## Running it

Requires Python 3.12+ with `numpy`, `pandas`, `scipy`, `statsmodels`, `matplotlib` and `pytest`.

```bash
python -m pytest harness/tests analysis/tests dashboard/tests -q      # no network, no cost
export KIN_ENV=/path/to/.env    # HF_TOKEN and ANTHROPIC_API_KEY
python -m harness.run_batch --mode swarm --kind smoke --n 4 --max-cost-usd 1
python -m harness.validate_batch runs/<batch_id>
python dashboard/server.py      # http://127.0.0.1:8765
```

Batches are written to `runs/` (gitignored). Monitor thresholds are not included, because they are derived from our pilot outcomes. Regenerate them from your own honest pilot batch (see `analysis/thresholds.py`). A pilot or main batch needs an approved `PREREG.md` hash, recorded in a `REVIEW_LOG.md` gate line (see `harness/run_batch.py`).

## Prior work and AI use

The project was built during the sprint, starting 6 November 2026. The code was written with an AI assistant (Claude). The design, review gates and report are the author's.

Author: James Balderson.
