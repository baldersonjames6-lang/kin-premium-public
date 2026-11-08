"""Figure 7 (EXPLORATORY, docs/ADDENDUM-1.md): leak rate by worker model and coordinator type.

Reads analysis/results/<main_batch>/addendum1.json (written by analysis/addendum1.py) and writes
figures/<main_batch>/fig7_addendum1_coordinator_type.png/.pdf, and appends the caption to captions.md.

    python -m analysis.fig_addendum1 2026-11-06T17-31-14Z_main
"""
import json
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

REPO = Path(__file__).resolve().parent.parent
TYPES = [("self", "Own model (kin_silent)", "#0072B2"),
         ("other_qwen", "Different Qwen model (Addendum 1)", "#E69F00"),
         ("other_family", "Different family (nonkin_silent)", "#D55E00")]
WORKERS = [("qwen9", "Qwen3.5-9B"), ("qwen27", "Qwen3.5-27B"), ("qwen35a3b", "Qwen3.5-35B-A3B")]


def main(batch: str) -> None:
    res = json.loads((REPO / "analysis" / "results" / batch / "addendum1.json").read_text())
    cells = res["by_worker_and_coord_type"]
    fig, ax = plt.subplots(figsize=(7.2, 3.8), dpi=150)
    w = 0.26
    for j, (t, label, colour) in enumerate(TYPES):
        xs, ys, lo, hi, txt = [], [], [], [], []
        for i, (wk, _) in enumerate(WORKERS):
            c = cells.get(f"{wk}|{t}")
            if not c:
                continue
            x = i + (j - 1) * w
            r = 100 * c["rate"]
            xs.append(x); ys.append(r)
            lo.append(r - 100 * c["ci95"][0]); hi.append(100 * c["ci95"][1] - r)
            txt.append((x, r, f"{c['k']}/{c['n']}"))
        ax.bar(xs, ys, w * 0.95, color=colour, label=label, yerr=[lo, hi], capsize=3, error_kw={"lw": 1})
        for x, r, s in txt:
            ax.text(x, min(r + 6, 103), s, ha="center", va="bottom", fontsize=7.5)
    ax.set_xticks(range(len(WORKERS)), [n for _, n in WORKERS])
    ax.set_xlabel("Worker model (all three workers in an episode)")
    ax.set_ylabel("Leak rate (%)")
    ax.set_ylim(0, 115)
    ax.spines[["top", "right"]].set_visible(False)
    ax.legend(fontsize=8, frameon=False, loc="upper right")
    ax.set_title("EXPLORATORY (Addendum 1, added after the main results)", fontsize=9, color="#555555", loc="left")
    fig.tight_layout()
    out = REPO / "figures" / batch
    for ext in ("png", "pdf"):
        fig.savefig(out / f"fig7_addendum1_coordinator_type.{ext}", dpi=300)
    cap = ("- **fig7_addendum1_coordinator_type** (png / pdf): Figure 7 (exploratory, not pre-registered). Leak rate by "
           "worker model when the coordinator is the workers' own model (kin_silent, main run), a different Qwen3.5 model "
           f"(Addendum 1 batch {res['explore_batch']}), or a model from a different family (nonkin_silent, main run); all "
           "without an identity sentence. Bars are raw rates with Wilson 95% CIs; labels are leaks/episodes. Qwen3.5-9B "
           "workers leak far less to their own model than to any other coordinator, including other Qwen models; the "
           "larger Qwen workers rarely leak to any Qwen coordinator. Source: analysis/addendum1.py, analysis/fig_addendum1.py.\n")
    cp = out / "captions.md"
    text = cp.read_text()
    if "fig7_addendum1" not in text:
        cp.write_text(text.rstrip("\n") + "\n" + cap)
    print("fig7 written")


if __name__ == "__main__":
    main(sys.argv[1])
