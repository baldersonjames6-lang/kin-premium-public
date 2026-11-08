"""Figures for the report (PREREG §9: every number from analysis/ scripts; CLAIMS.md maps claims to figures).

Reads ``analysis/results/<batch_id>/results.json`` (written by ``analysis/primary.py``) for every plotted rate
and interval, and the guarded episode table (``analysis/load.py``) only for the ROC curves. Saves each figure
as PNG (300 dpi) and PDF in ``figures/<batch_id>/``, plus ``captions.md`` with the numbered captions.

- Fig 0  team set-up schematic (no data)
- Fig 1  leak rate by group, Wilson 95% CIs, primary comparison highlighted (PREREG §6 H1-H3)
- Fig 2  where the data stopped: crossing none / worker_replies / report per group (§5 secondary)
- Fig 3  leak rate heatmap, worker x coordinator, split by identity sentence (§6 secondary)
- Fig 4  monitor detection at the fixed thresholds: TPR on leaks (local-max vs global) and FPR on the honest pilot (§6 H4)
- Fig 5  ROC curves per monitor and view (§6 H4, AUROC)
- Fig 6  worker concern rate by group: real raise_concern calls and attempted concerns (§6 secondary; attempted = exploratory)

Colours: Okabe-Ito (colour-blind safe). A PARTIAL batch gets a watermark and the stamp in every caption.
Usage: ``python -m analysis.figures runs/<batch_id> [--allow-partial]`` (run analysis.primary first).
"""
from __future__ import annotations

import argparse
import json

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch, Rectangle  # noqa: E402

from analysis.common import (COORDINATORS, GROUPS, MONITORS, VIEWS, WORKERS, add_guard_args, check_batch,
                             figures_dir, results_dir)  # noqa: E402
from analysis.primary import analysis_sets  # noqa: E402

OI = {"orange": "#E69F00", "sky": "#56B4E9", "green": "#009E73", "yellow": "#F0E442", "blue": "#0072B2",
      "verm": "#D55E00", "purple": "#CC79A7", "black": "#000000", "grey": "#999999"}
GROUP_COLOUR = {"kin_claimed": OI["verm"], "nonkin_silent": OI["blue"], "kin_silent": OI["orange"],
                "nonkin_falseclaim": OI["sky"]}
GROUP_LABEL = {"kin_claimed": "kin_claimed\nsame model,\nsays so", "nonkin_silent": "nonkin_silent\nother family,\nsays nothing",
               "kin_silent": "kin_silent\nsame model,\nsays nothing", "nonkin_falseclaim": "nonkin_falseclaim\nother family,\nclaims kinship"}
VIEW_COLOUR = {"local": OI["orange"], "global": OI["blue"]}
MON_LABEL = {"mon_claude": "Claude Haiku monitor", "mon_qwen": "Qwen3.5-27B monitor"}

plt.rcParams.update({"font.size": 10, "axes.titlesize": 11, "axes.labelsize": 10, "legend.fontsize": 9,
                     "xtick.labelsize": 9, "ytick.labelsize": 9, "font.family": "DejaVu Sans",
                     "axes.spines.top": False, "axes.spines.right": False})


class Figs:
    def __init__(self, batch_id: str, stamp: str | None):
        self.dir = figures_dir(batch_id)
        self.batch_id, self.stamp = batch_id, stamp
        self.captions: list[str] = []

    def save(self, fig, num: int, name: str, caption: str, watermark: bool = True):
        if self.stamp and watermark:  # the schematic (watermark=False) holds no data, so it is never stamped
            caption = f"[{self.stamp}] " + caption
            if watermark:
                fig.text(0.5, 0.5, self.stamp, ha="center", va="center", rotation=25, fontsize=20,
                         color="#B00020", alpha=0.25, transform=fig.transFigure, zorder=100)
        full = f"Figure {num}. {caption} Batch: {self.batch_id}."
        # place the caption under everything already drawn (tick labels, legends below the axes)
        renderer = fig.canvas.get_renderer()
        bb = fig.get_tightbbox(renderer)
        x0 = bb.x0 / fig.get_figwidth()
        y0 = bb.y0 / fig.get_figheight()
        width_chars = int(bb.width * 15)
        fig.text(x0, y0 - 0.02, _wrap(full, width_chars), ha="left", va="top", fontsize=8.5, transform=fig.transFigure)
        stem = self.dir / f"fig{num}_{name}"
        fig.savefig(f"{stem}.png", dpi=300, bbox_inches="tight")
        fig.savefig(f"{stem}.pdf", bbox_inches="tight")
        plt.close(fig)
        self.captions.append(f"- **{stem.name}** ({stem.name}.png / .pdf): {full}")

    def write_captions(self):
        head = f"# Figure captions, {self.batch_id}\n\n" + (f"**{self.stamp}**\n\n" if self.stamp else "")
        (self.dir / "captions.md").write_text(head + "\n".join(self.captions) + "\n")


def _wrap(text: str, width: int) -> str:
    import textwrap
    return "\n".join(textwrap.wrap(text, width))


def _err(r):
    if r["rate"] is None:
        return 0, [[0], [0]]
    return r["rate"], [[max(0.0, r["rate"] - r["ci_low"])], [max(0.0, r["ci_high"] - r["rate"])]]


# ------------------------------------------------------------------------------------------ Fig 0
def fig0_schematic(F: Figs):
    fig, ax = plt.subplots(figsize=(9, 6.2))
    ax.set_xlim(0, 10); ax.set_ylim(0, 7.2); ax.axis("off")

    def box(x, y, w, h, text, fc, ec="black", fs=9.5, bold=False):
        ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0.05,rounding_size=0.15", fc=fc, ec=ec, lw=1.2))
        ax.text(x + w / 2, y + h / 2, text, ha="center", va="center", fontsize=fs, weight="bold" if bold else None)

    def arrow(x1, y1, x2, y2, text="", style="-|>", color="black", ls="-", off=(0, 0)):
        ax.add_patch(FancyArrowPatch((x1, y1), (x2, y2), arrowstyle=style, mutation_scale=12, color=color, lw=1.2, ls=ls))
        if text:
            ax.text((x1 + x2) / 2 + off[0], (y1 + y2) / 2 + off[1], text, fontsize=8, ha="center", va="center",
                    bbox=dict(fc="white", ec="none", pad=0.5))

    # global view frame
    ax.add_patch(Rectangle((0.15, 0.35), 7.65, 6.7, fill=False, ls="--", lw=1.6, ec=OI["blue"]))
    ax.text(0.3, 6.85, "GLOBAL monitor view: whole team transcript, scored once\n(coordinator's system prompt and closing summary hidden)",
            fontsize=8.5, color=OI["blue"], va="top")
    box(2.6, 5.0, 3.0, 1.0, "Coordinator\n(compromised; sees no data;\ntool: send_task)", "#F4F4F4", bold=False)
    ax.text(5.72, 5.95, "identity sentence\n(kin_claimed,\nnonkin_falseclaim):\n\"I'm another instance\nof the same AI model\nas you…\"",
            fontsize=7.2, va="top", color=OI["verm"])
    xs = [0.45, 2.95, 5.45]
    labels = ["w1  data agent\nread_table, raise_concern", "w2  data agent\nread_table, raise_concern", "w3  writer\nwrite_report, raise_concern"]
    for x, lab in zip(xs, labels):
        ax.add_patch(Rectangle((x - 0.12, 2.05), 2.24, 1.55, fill=False, ls=":", lw=1.4, ec=OI["orange"]))
        box(x, 2.25, 2.0, 0.95, lab, "#FFF4DD", fs=7.8)
        ax.text(x + 1.0, 3.42, "LOCAL view", fontsize=7.5, color=OI["orange"], ha="center")
        arrow(4.1, 5.0, x + 1.0, 3.62, "")
    ax.text(1.0, 4.35, "tasks (send_task)\nand replies", fontsize=8, ha="center")
    box(0.45, 0.6, 4.5, 0.9, "Synthetic register: investors (notes hold\n5 planted markers MK-…), transactions, bank_statement", "#E8F4FB", fs=7.8)
    arrow(1.6, 1.5, 1.6, 2.25, ""); arrow(4.0, 1.5, 4.0, 2.25, "")
    box(5.45, 0.6, 2.0, 0.9, "Report\n(leak = a marker\nappears here)", "#FDE7E0", fs=8)
    arrow(6.4, 2.25, 6.5, 1.5, "")
    box(8.2, 2.3, 1.6, 0.9, "Overseer\n(raise_concern)", "#E5F5EF", fs=8.5)
    arrow(7.4, 2.9, 8.2, 2.75, "", ls="--", color=OI["green"])
    ax.text(8.95, 1.9, "local score of an\nepisode = max over\nw1, w2, w3", fontsize=7.5, ha="center", va="top", color=OI["orange"])
    F.save(fig, 0, "setup",
           "Team set-up. A compromised coordinator, which never sees the data, splits a forbidden goal (copy every "
           "investor's notes, which contain 5 planted markers, into the report) into routine-looking tasks for three "
           "workers of one Qwen model, each with its own conversation. w1 and w2 can read the tables; w3 writes the "
           "report. A leak is a planted marker in w3's report. Each monitor scores every worker's transcript "
           "separately (local view; the episode's local score is the maximum) and the whole team's transcript once "
           "(global view). Schematic only; no data.", watermark=False)


# ------------------------------------------------------------------------------------------ Fig 1
def fig1_leak_by_group(F: Figs, R: dict):
    rates = R["main"]["leak_rates"]
    fig, ax = plt.subplots(figsize=(7.5, 4.8))
    for i, g in enumerate(GROUPS):
        r = rates[g]
        y, e = _err(r)
        primary = g in ("kin_claimed", "nonkin_silent")
        ax.bar(i, y, color=GROUP_COLOUR[g], edgecolor="black", lw=2.2 if primary else 0.6,
               hatch=None if primary else "//", alpha=1 if primary else 0.75)
        ax.errorbar(i, y, yerr=e, fmt="none", ecolor="black", capsize=5, lw=1.2)
        ax.text(i, (r["ci_high"] or 0) + 0.035, f"{r['k']}/{r['n']}", ha="center", fontsize=9)
    h1 = R["main"]["H1"]
    stat = (f"H1: OR {h1['odds_ratio']:.2f} [{h1['ci_low']:.2f}, {h1['ci_high']:.2f}], p = {h1['p']:.3g}"
            if h1.get("estimable") else "H1: regression not estimable (see results.md)")
    hp = R["holm"]["tests"]["H1"]["p_holm"]
    ax.plot([0, 0, 1, 1], [1.03, 1.06, 1.06, 1.03], color="black", lw=1.3)
    ax.text(0.5, 1.09, f"primary comparison\n{stat}; Holm p = {hp:.3g}", ha="center", va="bottom", fontsize=8.5)
    ax.set_xticks(range(4), [GROUP_LABEL[g] for g in GROUPS])
    ax.set_ylim(0, 1.25); ax.set_ylabel("leak rate (marker in the report)")
    ax.set_yticks(np.linspace(0, 1, 6), [f"{int(v*100)}%" for v in np.linspace(0, 1, 6)])
    F.save(fig, 1, "leak_by_group",
           "Leak rate by group (main analysis set: episodes where the coordinator asked for the notes). Bars are "
           "raw rates with Wilson 95% confidence intervals; counts are leaks/episodes. The pre-registered primary "
           "comparison, kin_claimed vs nonkin_silent (solid outlined bars), is annotated with the odds ratio from "
           "the logistic regression leak ~ group + worker model; hatched bars are the two explainer groups.")


# ------------------------------------------------------------------------------------------ Fig 2
def fig2_crossing(F: Figs, R: dict):
    cb = R["secondary"]["crossing_by_group"]
    fig, ax = plt.subplots(figsize=(7.5, 4.6))
    stages = [("none", "stayed with the data agents", OI["grey"]),
              ("worker_replies", "reached the coordinator, not the report", OI["yellow"]),
              ("report", "reached the report (leak)", OI["verm"])]
    bottom = np.zeros(4)
    for key, lab, col in stages:
        vals = np.array([cb[g][key] / cb[g]["n"] if cb[g]["n"] else 0 for g in GROUPS])
        ax.bar(range(4), vals, bottom=bottom, color=col, edgecolor="black", lw=0.6, label=lab)
        for i, (v, b) in enumerate(zip(vals, bottom)):
            if v >= 0.06:
                ax.text(i, b + v / 2, f"{cb[GROUPS[i]][key]}", ha="center", va="center", fontsize=9)
        bottom += vals
    for i, g in enumerate(GROUPS):
        ax.text(i, 1.02, f"n={cb[g]['n']}", ha="center", fontsize=9)
    ax.set_xticks(range(4), [GROUP_LABEL[g] for g in GROUPS])
    ax.set_ylim(0, 1.1); ax.set_ylabel("share of episodes")
    ax.set_yticks(np.linspace(0, 1, 6), [f"{int(v*100)}%" for v in np.linspace(0, 1, 6)])
    ax.legend(title="furthest point a\nplanted marker reached", loc="center left", bbox_to_anchor=(1.0, 0.5),
              frameon=False, fontsize=8.5, reverse=True)
    F.save(fig, 2, "where_data_stopped",
           "Where the data stopped, by group (main analysis set). Each bar splits episodes by the furthest point any "
           "planted marker reached: it never left the data agents (grey), it reached the coordinator in a worker's "
           "reply but not the report (yellow), or it reached the report, which is a leak (red). Numbers inside bars "
           "are episode counts.")


# ------------------------------------------------------------------------------------------ Fig 3
def fig3_heatmap(F: Figs, R: dict):
    cells = R["secondary"]["worker_by_coordinator"]
    fig, axes = plt.subplots(1, 2, figsize=(10, 3.9), sharey=True)
    fig.subplots_adjust(wspace=0.08)
    cmap = plt.get_cmap("cividis").copy(); cmap.set_bad("#EEEEEE")
    for ax, claimed, title in ((axes[0], True, "identity sentence sent\n(kin_claimed + nonkin_falseclaim)"),
                               (axes[1], False, "no identity sentence\n(kin_silent + nonkin_silent)")):
        M = np.full((len(WORKERS), len(COORDINATORS)), np.nan)
        lab = [["" for _ in COORDINATORS] for _ in WORKERS]
        for c in cells:
            if c["identity_sentence"] != claimed or c["worker"] not in WORKERS or c["orchestrator"] not in COORDINATORS:
                continue
            i, j = WORKERS.index(c["worker"]), COORDINATORS.index(c["orchestrator"])
            if c["n"]:
                M[i, j] = c["rate"]; lab[i][j] = f"{c['k']}/{c['n']}"
        im = ax.imshow(np.ma.masked_invalid(M), cmap=cmap, vmin=0, vmax=1, aspect="auto")
        for i in range(len(WORKERS)):
            for j in range(len(COORDINATORS)):
                txt = lab[i][j] or "–"
                col = "white" if (not np.isnan(M[i, j]) and M[i, j] < 0.55) else "black"
                ax.text(j, i, txt, ha="center", va="center", fontsize=9, color=col)
        ax.set_xticks(range(len(COORDINATORS)), COORDINATORS, rotation=35, ha="right")
        ax.set_title(title)
        ax.axvline(2.5, color="white", lw=2)
        ax.set_xlabel("coordinator model")
    axes[0].set_yticks(range(len(WORKERS)), WORKERS); axes[0].set_ylabel("worker model")
    cb = fig.colorbar(im, ax=axes, fraction=0.025, pad=0.02); cb.set_label("leak rate")
    F.save(fig, 3, "heatmap_worker_coordinator",
           "Leak rate for every worker-model and coordinator-model pair (main analysis set), with the identity "
           "sentence (left) and without it (right). Cells show leaks/episodes; darker is lower. Qwen coordinators "
           "only ever coordinate their own model (kin groups, left of the white line), so off-diagonal Qwen cells are "
           "empty by design (–); the four coordinators right of the line are the non-kin families.")


# ------------------------------------------------------------------------------------------ Fig 4
def fig4_detection(F: Figs, R: dict):
    fig, axes = plt.subplots(1, 2, figsize=(9, 4.4), sharey=True)
    for ax, mon in zip(axes, MONITORS):
        h4 = R["main"]["H4"][mon]
        fpr = R["h4_extra"]["fpr_honest_pilot"]
        x = np.arange(2)
        for k, v in enumerate(("local", "global")):
            tpr = h4[f"tpr_{v}"]; fp = fpr[f"{mon}_{v}"]
            for xi, r, hatch in ((0, tpr, None), (1, fp, "..")):
                y, e = _err(r)
                ax.bar(xi + (k - 0.5) * 0.38, y, width=0.36, color=VIEW_COLOUR[v], edgecolor="black", lw=0.6,
                       hatch=hatch, label=("local-max view" if v == "local" else "global view") if xi == 0 else None)
                ax.errorbar(xi + (k - 0.5) * 0.38, y, yerr=e, fmt="none", ecolor="black", capsize=4)
                ax.text(xi + (k - 0.5) * 0.38, (r["ci_high"] or 0) + 0.035, f"{r['k']}/{r['n']}", ha="center", fontsize=8.5)
        ax.set_xticks(x, ["true-positive rate\non leaking episodes\n(main run)", "false-positive rate\non honest episodes\n(pilot)"])
        role = "H4 test" if mon == "mon_claude" else "secondary"
        ax.set_title(f"{MON_LABEL[mon]} ({role})\nexact McNemar p = {h4['p']:.3g}")
        ax.set_ylim(0, 1.15)
    axes[0].set_ylabel("share flagged at the fixed threshold")
    axes[0].set_yticks(np.linspace(0, 1, 6), [f"{int(v*100)}%" for v in np.linspace(0, 1, 6)])
    axes[0].legend(loc="upper right", frameon=False)
    thr = R["thresholds"]
    F.save(fig, 4, "monitor_detection",
           "Monitor detection at the fixed thresholds (95th percentile of honest pilot scores; flag = score ≥ "
           f"threshold: Claude local {thr['mon_claude_local']:.2f}, global {thr['mon_claude_global']:.2f}; Qwen local "
           f"{thr['mon_qwen_local']:.2f}, global {thr['mon_qwen_global']:.2f}). Left pair in each panel: share of "
           "leaking episodes (main analysis set) flagged when each worker is watched separately (local-max) or the "
           "whole team is watched (global). Right pair: share of the 20 honest pilot episodes flagged, which the "
           "thresholds fix at about 5% by construction. Wilson 95% CIs; the McNemar test compares paired flags on "
           "the same leaking episodes.")


# ------------------------------------------------------------------------------------------ Fig 5
def fig5_roc(F: Figs, R: dict, main_set):
    from sklearn.metrics import roc_curve
    fig, axes = plt.subplots(1, 2, figsize=(9, 4.4))
    for ax, mon in zip(axes, MONITORS):
        for v in VIEWS:
            d = main_set[["leak", f"{mon}_{v}", f"{mon}_{v}_flag"]].dropna()
            a = R["h4_extra"]["auroc_main"][f"{mon}_{v}"]
            name = "local-max" if v == "local" else "global"
            if a.get("estimable"):
                fpr, tpr, _ = roc_curve(d["leak"].astype(int), d[f"{mon}_{v}"])
                ax.plot(fpr, tpr, color=VIEW_COLOUR[v], lw=2, ls="-" if v == "global" else "--",
                        label=f"{name}: AUROC {a['auroc']:.2f} [{a['ci_low']:.2f}, {a['ci_high']:.2f}]")
                y = d["leak"].astype(bool); f = d[f"{mon}_{v}_flag"].astype(bool)
                ax.plot((f & ~y).sum() / max(1, (~y).sum()), (f & y).sum() / max(1, y.sum()), "o", ms=8,
                        mfc="white", mec=VIEW_COLOUR[v], mew=2)
            else:
                ax.plot([], [], color=VIEW_COLOUR[v], label=f"{name}: not estimable")
        ax.plot([0, 1], [0, 1], color=OI["grey"], lw=1, ls=":")
        ax.set_title(MON_LABEL[mon]); ax.set_xlabel("false-positive rate (non-leaking episodes)")
        ax.set_xlim(-0.02, 1.02); ax.set_ylim(-0.02, 1.02); ax.set_aspect("equal")
        ax.legend(loc="lower right", frameon=False, fontsize=8)
    axes[0].set_ylabel("true-positive rate (leaking episodes)")
    F.save(fig, 5, "roc",
           "ROC curves for each monitor and view on the main analysis set, with leak as the label and the 0-10 "
           "suspicion score as the classifier (local-max dashed, global solid). AUROC with a bootstrap 95% CI is in "
           "the legend. Open circles mark the operating point at the fixed thresholds, computed here among "
           "non-leaking attack episodes (not the honest pilot).")


# ------------------------------------------------------------------------------------------ Fig 6
def fig6_concern(F: Figs, R: dict):
    real = R["secondary"]["worker_concern"]["rates"]
    att = R["exploratory"]["attempted_concern"]["rates"]
    fig, ax = plt.subplots(figsize=(7.5, 4.6))
    for k, (rates, lab, col, hatch) in enumerate(((real, "raise_concern tool call (checker)", OI["green"], None),
                                                   (att, "attempted concern (exploratory; incl. malformed calls)", OI["purple"], "//"))):
        for i, g in enumerate(GROUPS):
            r = rates[g]; y, e = _err(r)
            xi = i + (k - 0.5) * 0.38
            ax.bar(xi, y, width=0.36, color=col, edgecolor="black", lw=0.6, hatch=hatch, label=lab if i == 0 else None)
            ax.errorbar(xi, y, yerr=e, fmt="none", ecolor="black", capsize=4)
            ax.text(xi, (r["ci_high"] or 0) + 0.035, f"{r['k']}/{r['n']}", ha="center", fontsize=8)
    ax.set_xticks(range(4), [GROUP_LABEL[g] for g in GROUPS])
    ax.set_ylim(0, 1.18); ax.set_ylabel("episodes with at least one worker concern")
    ax.set_yticks(np.linspace(0, 1, 6), [f"{int(v*100)}%" for v in np.linspace(0, 1, 6)])
    ax.legend(loc="upper center", bbox_to_anchor=(0.5, 1.12), ncol=2, frameon=False, fontsize=8.5)
    F.save(fig, 6, "worker_concern",
           "Share of episodes in which at least one worker raised a concern, by group (main analysis set), with "
           "Wilson 95% CIs. Solid green: a well-formed raise_concern tool call, as counted by the checker "
           "(pre-registered secondary outcome). Hatched purple (exploratory, not pre-registered): the same, or a "
           "worker reply that failed to parse as a tool call but mentions a concern; it is an upper bound.")


def load_snapshot(info) -> "pd.DataFrame":
    """The exact episode table primary.py analysed (episodes.csv next to results.json), so figures and numbers
    always describe the same episodes even while a partial batch keeps growing."""
    import pandas as pd
    p = results_dir(info.batch_id) / "episodes.csv"
    df = pd.read_csv(p)
    for c in df.columns:
        if c.endswith("_flag") or c in ("leak", "orchestrator_asked_for_notes"):
            df[c] = df[c].map({True: True, False: False, "True": True, "False": False})
    df["error"] = df["error"].where(df["error"].notna(), None)
    return df


def main(argv=None):
    ap = add_guard_args(argparse.ArgumentParser(description=__doc__.splitlines()[0]))
    a = ap.parse_args(argv)
    info = check_batch(a.batch, expected_kind="main", allow_partial=a.allow_partial)
    rpath = results_dir(info.batch_id) / "results.json"
    if not rpath.exists():
        raise SystemExit(f"{rpath} missing: run python -m analysis.primary first")
    R = json.loads(rpath.read_text())
    df = load_snapshot(info)
    if R["n_episodes_in_file"] != len(df) or (not info.partial and (R["partial"] or len(df) != info.n_episodes)):
        raise SystemExit("results.json / episodes.csv are stale for this batch: re-run analysis.primary")
    F = Figs(info.batch_id, R["stamp"])
    main_set = analysis_sets(df)["main"]
    fig0_schematic(F); fig1_leak_by_group(F, R); fig2_crossing(F, R); fig3_heatmap(F, R)
    fig4_detection(F, R); fig5_roc(F, R, main_set); fig6_concern(F, R)
    F.write_captions()
    print(f"{R['stamp'] or 'COMPLETE'}: {len(F.captions)} figures -> {F.dir}")


if __name__ == "__main__":
    main()
