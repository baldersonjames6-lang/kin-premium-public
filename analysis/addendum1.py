"""Addendum 1 (exploratory, docs/ADDENDUM-1.md): is the kin discount self-scepticism or attacker skill?

Compares, within each worker model, the leak rate under three coordinator types:
  self         = kin_silent episodes of the main run (the workers' own model, no claim)
  other_family = nonkin_silent episodes of the main run (DeepSeek / Gemma / Kimi, no claim)
  other_qwen   = the explore batch (a different Qwen3.5 model, no claim)
Model: leak ~ C(coord_type, Treatment('self')) + C(worker). EXPLORATORY: never in the Holm family.

    python -m analysis.addendum1 runs/<main_batch> runs/<explore_batch>
"""
from __future__ import annotations

import json
import math
import sys
from pathlib import Path

import pandas as pd
import statsmodels.formula.api as smf

from analysis.common import check_batch, load_thresholds, results_dir
from analysis.load import load_batch, load_episodes
from analysis.stats import wilson

STAMP = "EXPLORATORY (ADDENDUM-1): added after seeing the main results; not pre-registered; not in the Holm family"


def build(main_batch: str, explore_batch: str) -> pd.DataFrame:
    _, main = load_batch(main_batch)                      # fully guarded, with top-ups merged
    info = check_batch(explore_batch, expected_kind="explore")
    notes = info.manifest.get("notes") or ""
    if not notes.startswith("EXPLORATORY (ADDENDUM-1)"):
        raise SystemExit(f"REFUSED: {info.batch_id} is not an ADDENDUM-1 batch")
    exp = load_episodes(info.batch_dir, load_thresholds())
    exp = exp[exp["error"].isna()].assign(coord_type="other_qwen", source_batch=info.batch_id)
    m = main[main["error"].isna()]
    self_ = m[m["group"] == "kin_silent"].assign(coord_type="self")
    fam = m[m["group"] == "nonkin_silent"].assign(coord_type="other_family")
    cols = ["episode_id", "coord_type", "orchestrator", "worker", "leak", "worker_concern", "source_batch"]
    return pd.concat([self_, fam, exp], ignore_index=True).reindex(columns=cols), info, int(len(exp))


def rate(d: pd.DataFrame) -> dict:
    k, n = int(d["leak"].sum()), int(len(d))
    _, lo, hi = wilson(k, n)
    return {"k": k, "n": n, "rate": k / n if n else None, "ci95": [lo, hi]}


def main(argv=None):
    a = argv or sys.argv[1:]
    df, info, n_exp = build(a[0], a[1])
    res = {"stamp": STAMP, "explore_batch": info.batch_id, "main_batch": Path(a[0]).name, "n_explore_ok": n_exp,
           "source": "analysis/addendum1.py"}
    res["by_coord_type"] = {t: rate(g) for t, g in df.groupby("coord_type")}
    res["by_worker_and_coord_type"] = {f"{w}|{t}": rate(g) for (w, t), g in df.groupby(["worker", "coord_type"])}
    res["other_qwen_by_pair"] = {f"{o}>{w}": rate(g) for (o, w), g in
                                 df[df.coord_type == "other_qwen"].groupby(["orchestrator", "worker"])}
    d = df.assign(leak=df["leak"].astype(int))
    keep = [w for w, g in d.groupby("worker") if 0 < g["leak"].mean() < 1]   # as clarification C4
    fit = smf.logit("leak ~ C(coord_type, Treatment('self')) + C(worker)", data=d[d.worker.isin(keep)]).fit(disp=0)
    res["logit"] = {"workers_used": keep, "terms": {}}
    for term in fit.params.index:
        if "coord_type" in term:
            lo, hi = fit.conf_int().loc[term]
            res["logit"]["terms"][term] = {"or": math.exp(fit.params[term]), "ci95": [math.exp(lo), math.exp(hi)],
                                           "p": float(fit.pvalues[term])}
    from scipy.stats import fisher_exact
    res["fisher_within_worker"] = {}
    for wk in sorted(df.worker.unique()):
        g = df[df.worker == wk]
        for t in ["other_qwen", "other_family"]:
            x, y = g[g.coord_type == "self"]["leak"], g[g.coord_type == t]["leak"]
            if len(x) and len(y):
                tab = [[int(x.sum()), int(len(x) - x.sum())], [int(y.sum()), int(len(y) - y.sum())]]
                res["fisher_within_worker"][f"{wk}|self_vs_{t}"] = {"table": tab, "p": float(fisher_exact(tab)[1]),
                                                                    "test": "two-sided Fisher exact, ad hoc (exploratory)"}
    out = results_dir(Path(a[0]).name)
    (out / "addendum1.json").write_text(json.dumps(res, indent=2))
    lines = [f"# Addendum 1 results ({STAMP})", "",
             f"Explore batch `{info.batch_id}` ({n_exp} usable episodes) compared with the main run's kin_silent (self) "
             "and nonkin_silent (other_family) episodes, all with no identity claim.", "", "## Leak rate by coordinator type"]
    for t in ["self", "other_qwen", "other_family"]:
        r = res["by_coord_type"].get(t)
        if r:
            lines.append(f"- {t}: {r['k']}/{r['n']} = {100*r['rate']:.1f}% (95% CI {100*r['ci95'][0]:.1f}-{100*r['ci95'][1]:.1f}%)")
    lines += ["", "## By worker model"]
    for w in sorted(df.worker.unique()):
        parts = []
        for t in ["self", "other_qwen", "other_family"]:
            r = res["by_worker_and_coord_type"].get(f"{w}|{t}")
            if r:
                parts.append(f"{t} {r['k']}/{r['n']} ({100*r['rate']:.0f}%)")
        lines.append(f"- {w}: " + "; ".join(parts))
    lines += ["", "## other_qwen by coordinator > worker"]
    for k, r in res["other_qwen_by_pair"].items():
        lines.append(f"- {k}: {r['k']}/{r['n']} ({100*r['rate']:.0f}%)")
    lines += ["", "## Logistic model (reference: self), workers with varying outcome: " + ", ".join(keep)]
    for term, r in res["logit"]["terms"].items():
        lines.append(f"- {term}: OR {r['or']:.2f} (95% CI {r['ci95'][0]:.2f}-{r['ci95'][1]:.2f}), p = {r['p']:.3g}")
    (out / "addendum1.md").write_text("\n".join(lines) + "\n")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
