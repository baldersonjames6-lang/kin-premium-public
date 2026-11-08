"""Run the whole pre-registered analysis for one main batch (PREREG §6 tests, §9 reporting), in order:

1. ``analysis.primary``  -> analysis/results/<batch_id>/results.json, results.md, episodes.csv
2. ``analysis.figures``  -> figures/<batch_id>/fig0..fig6 (.png 300 dpi, .pdf) and captions.md
3. ``analysis.claims``   -> CLAIMS.md (numbers only from a complete batch; otherwise "PENDING main run")

    python -m analysis.run_all runs/2026-11-06T17-31-14Z_main                  # the real thing
    python -m analysis.run_all runs/2026-11-06T17-31-14Z_main --allow-partial  # development; all outputs PARTIAL

Every step re-applies the guard in ``analysis/common.py`` (kind main, status complete, SHA256SUMS intact,
prereg_sha256 = sha256 of the current PREREG.md). With --allow-partial, claims.py still refuses and writes
placeholders.
"""
from __future__ import annotations

import argparse

from analysis import claims, figures, primary
from analysis.common import add_guard_args


def main(argv=None):
    a = add_guard_args(argparse.ArgumentParser(description=__doc__.splitlines()[0])).parse_args(argv)
    extra = ["--allow-partial"] if a.allow_partial else []
    primary.main([a.batch, *extra])
    figures.main([a.batch, *extra])
    claims.main([a.batch])


if __name__ == "__main__":
    main()
