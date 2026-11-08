# Review dashboard

A local web app for reviewing the kin-premium experiment: the six review gates, live runs, playback, blind labelling, the code, data integrity, and a guide for writing the report. It also has a read-only assistant.

## Start it (one command, from the repo root)

```bash
~/42-workspace/experiments/apart-swarm-2026/.venv-py314/bin/python dashboard/server.py
```

It listens on **127.0.0.1:8765 only**. From your laptop:

```bash
ssh -L 8765:127.0.0.1:8765 mini42
```

Then open http://localhost:8765.

- **Dependencies:** only the standard library. If `pygments` and `markdown-it-py` are installed (both are in that venv), you also get syntax highlighting and rendered Markdown; without them it falls back to plain text.
- **No CDNs:** the front end is plain JS and CSS in `static/`, using system fonts.

## What it reads and writes

| | Path | How |
|---|---|---|
| reads | `PREREG.md`, `docs/CONTRACTS.md`, `CLAIMS.md`, `figures/`, `data/<seed>/`, `harness/`, `analysis/`, `runs/<batch>/` | read-only |
| appends | `REVIEW_LOG.md` | one block per gate decision |
| appends | `runs/<batch>/human_labels.jsonl` | one line per blind label |
| writes | `docs/report/<section>.md` | your drafts, with a copy in `docs/report/.history/` on every save |
| writes | `dashboard/.state/` | checklist ticks, a snapshot of PREREG.md at sign-off, the pytest junit report, assistant token usage |

- **Starting batches:** it only ever runs `python -m harness.run_batch --kind <kind> --max-cost-usd <cap> [--n N]`, or the FAKE demo runner.
- **Kinds:** smoke always runs. Pilot and main need gate 1 approved in REVIEW_LOG.md, and `run_batch.py` applies its own REVIEW_LOG check on top, which the dashboard can't bypass.
- **Stop:** sends SIGINT to the process group.
- **Confirmation:** every real run needs a second click that states the kind and the cost cap.

## Sections
1. **Guide:** the single next action, then the six gates in order. Each gate has why it matters, automatic checks, your checklist, the evidence inline, and Approve or Request changes.
   - **Gate 3 evidence:** gate 3 also shows the requests actually sent in real batches, with an automatic check that they're identical once the identity sentence is removed.
   - **If PREREG changes after sign-off:** gate 1 goes stale and shows a diff against the signed text.
2. **Live run:** pick the kind, the episode count and the cost cap. It shows a 4×4 requester × peer grid that fills with outcome shapes (a ring marks a monitor flag), the spend against the cap and the £100 ceiling, the latest episodes and the harness output.
3. **Playback:** a catalogue of every batch and episode with filters.
   - **Replay:** an episode replays on a timeline (Space, ← →, Home, End), with node colours derived from what has happened so far, full content, collapsible reasoning text and highlighted markers.
   - **Sources:** hover any number to see its file and line.
4. **Blind review:** the transcript only. The models, the condition, the monitors, the verdict and the marker highlights are hidden until you label (keys 1 to 5, then Enter).
   - **Live statistics:** raw agreement, Cohen's κ, a confusion matrix and the list of disagreements.
   - **Samples:** the pilot sample is every attack episode of the pilot (honest-baseline episodes excluded). The audit sample is a seeded random 5% of the main run, so it is reproducible.
5. **Code:** `harness/`, `analysis/` and the docs, with highlighting, line links (`#/code/harness/checker.py:40`) and `git log --oneline -30`.
6. **Data integrity:** every batch's SHA256SUMS is re-hashed on each visit. It also shows unlisted files, the count against the manifest, the PREREG hash against the signed hash, whether each batch is eligible for analysis, and where every file lives.
7. **Results and report:** figures, CLAIMS.md with links, and the Apart template section by section.
   - **Per section:** the template's guidance, project pointers, relevant claims, a word target and the page budget.
   - **Editor:** a box that autosaves your text. The dashboard never writes prose.
8. **Assistant** (`/` or "Ask about this"): it sends your question and the context on screen to `claude-haiku-5-5`.
   - **Key:** read server-side from the .env at `KIN_ENV` and never sent to the browser.
   - **Read-only:** no tools.
   - **Blind episodes:** the verdict is withheld while you are labelling.
   - **Spend:** a daily cap (`KIN_ASSIST_BUDGET_USD`, default $5).

## REVIEW_LOG block format
```
## Gate 1 · Pre-registration sign-off · APPROVED
<!-- kin-review gate=1 decision=approved time=2026-11-06T21:00:00Z prereg_sha256=<sha> -->
- **Time (UTC):** …
- **Decision:** approved
- **Note:** …
- **PREREG.md sha256 at this decision:** `<sha>`
- **Evidence (sha256):**
  - `PREREG.md` `<sha>`
```
- **Which line the harness reads:** only gate 1's machine line carries `prereg_sha256=`. That's the line `harness/run_batch.py` treats as PREREG approval: it needs the current hash and "approv" on the same line.
- **Later gates:** never put the hash and "approved" on the same line.
- **Latest decision wins:** the dashboard uses the latest decision for each gate.

## Swarm (decomposition) design: what changed in the dashboard
The experiment now runs one compromised orchestrator and three workers (w1, w2 data agents; w3 report writer), `run_batch --mode swarm`. Old single-prompt batches still show, labelled **single-prompt (v1 design, baseline)**; spike/smoke/calibrate batches are marked **never analysed**.
- **Playback** (`static/js/swarm.js`): orchestrator on top, w1/w2/w3 below, plus tables, overseer and the REPORT sink. Edges animate per `send_task` / reply / tool call; red edges are the path the markers took. Node colour builds up step by step: red = markers passed through it (its replies, or a leaking report), amber = it received markers in a task, green = it raised a concern, grey otherwise. The final colours equal `outcome.per_worker` (server `worker_status`). Click a node for its panel: system prompt, tasks, tool calls, replies, concerns and its LOCAL monitor scores. The header shows leak, objective_met, crossing, local_red_flags and GLOBAL vs LOCAL-max for both monitors. The orchestrator's hidden objective is shown to you, labelled "hidden from workers and monitors".
- **Catalogue filters:** batch, kind, mode, group, variant, orchestrator, worker, kinship, claim, outcome, crossing. A stale saved filter value is dropped, so it can't silently empty the table.
- **Live run:** mode Swarm (smoke, spike, pilot, main) or Single-prompt v1 (smoke only). Variant picker for swarm smoke/spike. Planned sizes are read from `python -m harness.run_batch --mode swarm --kind <k> --dry-run`, never hard-coded. The grid is workers (rows) × orchestrators (cols), from the episodes seen plus the planned pilot/main grid; unknown model keys are just added. Pilot/main stay locked unless gate 1 is approved for the current PREREG hash, and `run_batch.py` keeps its own refusal.
- **Blind review:** the sample is the attack episodes (`variant != honest`). Hidden: outcome, monitors, models (incl. `meta`), claim and group, the orchestrator's system prompt, its closing summary and its reasoning, and the identity line on every task. Shown: the team transcript with speaker labels, plus the final report. Spike/smoke batches can be labelled as practice (mode `spike`); old v1 pilots get mode `v1_pilot`. Neither ever counts for gate 4.
- **Gates:** gate 2–6 decisions now carry `design=swarm` on their machine line. v1 approvals stay in REVIEW_LOG.md (shown as "v1 design, superseded") but no longer count, and checklist ticks are kept per design (`swarm:<gate>`). Gate 1 diffs PREREG.md against the version you last reviewed (the snapshot taken at any gate-1 decision, or a matching `docs/PREREG*.md`). Gate 2 adds the `harness/tests/test_swarm.py` results. Gate 3 renders the worker, coordinator (main variant and honest) and monitor prompts and the identity lines live from `harness/prompts.py` and `harness/conditions.py`, and checks the real swarm events (identity line at the start of every task; no monitor prompt contains the hidden objective).
- **Temp labels:** `KIN_LABELS_DIR=<dir>` sends blind labels to `<dir>/<batch>/human_labels.jsonl` instead of `runs/`. Tests and UI checks only; the UI shows a TEST MODE bar.

## FAKE demo data
`dev_fixtures/` holds synthetic batches for building and testing the UI: `DEMO-fixture` (68 episodes) and `DEMO-fixture-tampered` (one file altered after hashing, so it shows a red cross).
- **Regenerate:** `python dashboard/dev_fixtures/make_fixture.py`.
- **How they're kept apart:** they have kind `demo`, live outside `runs/`, and are marked FAKE everywhere they are shown. They are never eligible for analysis, and they never count towards a gate.
- **Hide them:** use the toggle in the sidebar.
- **Demo run:** "FAKE demo" on Live run writes `dev_fixtures/runs/DEMO-live-*` with no model calls.

## Testing without touching the real log
```bash
KIN_REVIEW_LOG=/tmp/kp/REVIEW_LOG.md KIN_STATE_DIR=/tmp/kp/state KIN_REPORT_DIR=/tmp/kp/report \
  ~/42-workspace/experiments/apart-swarm-2026/.venv-py314/bin/python dashboard/server.py
```
- **Test-mode banner:** when the log is overridden, the guide shows a TEST MODE banner. `run_batch.py` still checks the real `REVIEW_LOG.md`, so test approvals can't unlock real pilot or main runs.
- **Unit tests:** `python -m pytest dashboard/tests -q`.

## Environment variables
- `KIN_PORT` (default 8765)
- `KIN_REPO`
- `KIN_ENV` (the .env holding the API key)
- `KIN_REVIEW_LOG`
- `KIN_REPORT_DIR`
- `KIN_STATE_DIR`
- `KIN_LABELS_DIR` (temp blind-label dir; tests and UI checks only)
- `KIN_PYTHON` (the interpreter for the harness and tests)
- `KIN_ASSIST_MODEL`
- `KIN_ASSIST_BUDGET_USD`
- `KIN_GBP_USD` (default 1.27, used only to show the £100 ceiling in dollars)
