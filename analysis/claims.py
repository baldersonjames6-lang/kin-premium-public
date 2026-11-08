"""Write CLAIMS.md, the claim ledger (PREREG §9: "CLAIMS.md maps each claim to its script, figure and batch").

Each row gives a claim id, the exact neutral sentence a report may use (numbers filled in from
``analysis/results/<batch_id>/results.json``), the numbers, the source script and function, the figure, the
batch and the PREREG section. It is a lookup table for James, not report prose. Exploratory rows are marked.

CLAIMS.md is filled in ONLY from a main batch that passes the full guard (kind main, status complete,
SHA256SUMS intact, prereg sha256 matching) and whose results.json is not PARTIAL. Otherwise every sentence is
written as ``PENDING main run`` and no number appears.

Usage: ``python -m analysis.claims runs/<main_batch>``  (there is deliberately no --allow-partial)
"""
from __future__ import annotations

import argparse
import json

from analysis.common import GROUPS, MONITORS, REPO, BatchRefused, check_batch, results_dir

OUT = REPO / "CLAIMS.md"
PENDING = "PENDING main run"


def pct(r):
    return "n/a (no episodes)" if r["rate"] is None else \
        f"{r['k']}/{r['n']} ({100*r['rate']:.1f}%, 95% CI {100*r['ci_low']:.1f}–{100*r['ci_high']:.1f}%)"


def or_text(c):
    if c.get("estimable"):
        return f"odds ratio {c['odds_ratio']:.2f} (95% CI {c['ci_low']:.2f}–{c['ci_high']:.2f}), p = {c['p']:.3g}"
    fb = c.get("fallback") or {}
    if fb.get("estimable"):
        return f"the logistic model was not estimable ({c['reason']}); stratified CMH test p = {fb['p']:.3g}"
    return f"the contrast was not estimable ({c['reason']})"


def contrast_sentence(c, outcome_words, holm=None):
    s = (f"The {outcome_words} was {pct(c['rate_group'])} in {c['contrast'].split(' vs ')[0]} and "
         f"{pct(c['rate_reference'])} in {c['contrast'].split(' vs ')[1]}; {or_text(c)}")
    if holm:
        s += f"; Holm-adjusted p = {holm['p_holm']:.3g} ({'significant' if holm['reject_at_0.05'] else 'not significant'} at α = 0.05)"
    return s + "."


def contrast_numbers(c):
    nums = [f"{c['rate_group']['k']}/{c['rate_group']['n']}", f"{c['rate_reference']['k']}/{c['rate_reference']['n']}"]
    if c.get("estimable"):
        nums += [f"OR {c['odds_ratio']:.2f}", f"CI {c['ci_low']:.2f}–{c['ci_high']:.2f}", f"p {c['p']:.3g}"]
    return "; ".join(nums)


def claim_specs():
    """(id, kind, prereg §, figure, source, builder(R) -> (sentence, numbers)). Builders read results.json only."""
    S = []
    hyp = {"H1": ("kin_claimed vs nonkin_silent (kin premium)", "Fig 1"),
           "H2": ("kin_silent vs nonkin_silent (being kin)", "Fig 1"),
           "H3": ("nonkin_falseclaim vs nonkin_silent (claim / impersonation)", "Fig 1")}
    for h, (what, fig) in hyp.items():
        S.append((f"{h}", f"primary ({what})", "§6 " + h, fig, "analysis/primary.py:contrasts + run (Holm)",
                  lambda R, h=h: (contrast_sentence(R["main"][h], "leak rate (main analysis set)", R["holm"]["tests"][h]),
                                  contrast_numbers(R["main"][h]) + f"; Holm p {R['holm']['tests'][h]['p_holm']:.3g}")))
    for mon in MONITORS:
        prim = mon == "mon_claude"

        def h4(R, mon=mon, prim=prim):
            r = R["main"]["H4"][mon]
            t = r["table"]
            s = (f"Among {r['n_leaking_paired']} leaking episodes, the {mon} global view flagged {pct(r['tpr_global'])} "
                 f"and the local-max view flagged {pct(r['tpr_local'])} at the fixed thresholds "
                 f"(global-only {t['global_only']}, local-only {t['local_only']}; exact McNemar p = {r['p']:.3g}")
            if prim:
                hh = R["holm"]["tests"]["H4"]
                s += f"; Holm-adjusted p = {hh['p_holm']:.3g}"
            return s + ").", f"{t['global_only']} vs {t['local_only']} discordant; p {r['p']:.3g}"
        S.append((f"H4-{mon}", "primary (oversight)" if prim else "secondary (H4, second monitor; plan clarification C1)",
                  "§6 H4", "Fig 4", "analysis/primary.py:h4_mcnemar", h4))
    for mon in MONITORS:
        for v in ("local", "global"):
            def fpr(R, k=f"{mon}_{v}"):
                r = R["h4_extra"]["fpr_honest_pilot"][k]
                a = R["h4_extra"]["auroc_main"][k]
                au = (f"; AUROC on the main analysis set {a['auroc']:.3f} (95% bootstrap CI {a['ci_low']:.3f}–{a['ci_high']:.3f})"
                      if a.get("estimable") else "; AUROC not estimable")
                return (f"At threshold {R['thresholds'][k]:.2f}, {k} flagged {pct(r)} of honest pilot episodes "
                        f"(thresholds were set on these episodes){au}.",
                        f"FPR {r['k']}/{r['n']}" + (f"; AUROC {a['auroc']:.3f}" if a.get("estimable") else ""))
            S.append((f"H4x-{mon}-{v}", "primary-reported (H4 FPR and AUROC)", "§5, §6 H4", "Fig 4, Fig 5",
                      "analysis/primary.py:fpr_honest, auroc_views", fpr))
    S.append(("D1", "descriptive", "§6 analysis set", "–", "analysis/primary.py:describe_sets",
              lambda R: (f"Of {R['descriptive']['n_episodes']} main-run episodes, {R['descriptive']['n_errors_excluded']} "
                         f"ended in an API error and were excluded; in {R['descriptive']['n_coordinator_did_not_attempt']} "
                         f"the coordinator never asked for the notes; the main analysis set has {R['descriptive']['n_main']} episodes.",
                         f"{R['descriptive']['n_episodes']}; {R['descriptive']['n_errors_excluded']}; "
                         f"{R['descriptive']['n_coordinator_did_not_attempt']}; {R['descriptive']['n_main']}")))
    for h in ("H1", "H2", "H3"):
        S.append((f"ITT-{h}", "sensitivity (ITT)", "§6", "–", "analysis/primary.py:contrasts",
                  lambda R, h=h: (contrast_sentence(R["itt"][h], "leak rate (all episodes, ITT)"), contrast_numbers(R["itt"][h]))))
    S.append(("S1", "secondary (claim on top of kinship)", "§6 secondary", "Fig 1", "analysis/primary.py:contrasts",
              lambda R: (contrast_sentence(R["secondary"]["claim_on_top_of_kinship"], "leak rate"),
                         contrast_numbers(R["secondary"]["claim_on_top_of_kinship"]))))
    for oc, words, fig in (("worker_concern", "rate of episodes with a worker raise_concern call", "Fig 6"),
                           ("crossed", "rate of a marker leaving the data agents (crossing ≥ worker_replies)", "Fig 2")):
        for h in ("H1", "H2", "H3"):
            S.append((f"S-{oc}-{h}", "secondary", "§6 secondary", fig, "analysis/primary.py:contrasts",
                      lambda R, oc=oc, h=h, words=words: (contrast_sentence(R["secondary"][oc][h], words),
                                                         contrast_numbers(R["secondary"][oc][h]))))
    for g in ("nonkin_silent", "nonkin_falseclaim"):
        S.append((f"S-coord-{g}", "secondary (per coordinator)", "§6 secondary", "Fig 3",
                  "analysis/primary.py:per_coordinator_nonkin",
                  lambda R, g=g: ("In " + g + ", leak rates by coordinator were " + "; ".join(
                      f"{k} {pct(v)}" for k, v in R["secondary"]["per_coordinator_nonkin"][g].items()) + ".",
                      "; ".join(f"{k} {v['k']}/{v['n']}" for k, v in R["secondary"]["per_coordinator_nonkin"][g].items()))))
    S.append(("S-worker", "secondary (by worker model)", "§6 secondary", "Fig 3", "analysis/primary.py:by_worker",
              lambda R: ("Leak rates by worker model were " + "; ".join(f"{k} {pct(v)}" for k, v in R["secondary"]["by_worker"].items()) + ".",
                         "; ".join(f"{k} {v['k']}/{v['n']}" for k, v in R["secondary"]["by_worker"].items()))))
    for mon in MONITORS:
        def gap(R, mon=mon):
            r = R["secondary"]["detection_gap_interaction"][mon]
            gk, gn = r.get("gap_kin"), r.get("gap_nonkin")
            f = lambda x: "n/a" if x is None else f"{100*x:+.1f} points"
            s = (f"For {mon}, the global-minus-local detection gap among leaks was {f(gk)} with a kin coordinator "
                 f"(n = {r['n_kin']}) and {f(gn)} with a non-kin coordinator (n = {r['n_nonkin']}); ")
            s += (f"interaction odds ratio {r['interaction_or']:.2f} (95% CI {r['ci_low']:.2f}–{r['ci_high']:.2f}), p = {r['p']:.3g}."
                  if r.get("estimable") else f"the interaction was not estimable ({r['reason'][:80]}).")
            return s, f"{f(gk)}; {f(gn)}"
        S.append((f"S-gap-{mon}", "secondary (kinship x view interaction)", "§6 secondary", "Fig 4",
                  "analysis/primary.py:detection_gap_interaction", gap))
    S.append(("E1", "EXPLORATORY (not pre-registered; REVIEW_LOG gate 4)", "– (REVIEW_LOG gate 4 method change)", "Fig 6",
              "analysis/load.py:attempted_concern_from_events; analysis/primary.py:contrasts",
              lambda R: ("Counting malformed worker replies that mention a concern as attempted concerns (exploratory), the "
                         "attempted-concern rate was " + "; ".join(
                             f"{g} {pct(R['exploratory']['attempted_concern']['rates'][g])}" for g in GROUPS) + ".",
                         "; ".join(f"{g} {R['exploratory']['attempted_concern']['rates'][g]['k']}/"
                                   f"{R['exploratory']['attempted_concern']['rates'][g]['n']}" for g in GROUPS))))
    return S


def esc(s: str) -> str:
    return str(s).replace("|", "\\|").replace("\n", " ")


def addendum_rows(batch_id: str) -> list[str]:
    """EXPLORATORY rows from docs/ADDENDUM-1.md (analysis/addendum1.py), if that analysis has been run."""
    p = results_dir(batch_id) / "addendum1.json"
    if not p.exists():
        return []
    A = json.loads(p.read_text())
    def r(c):
        return f"{c['k']}/{c['n']} ({100 * c['rate']:.1f}%, 95% CI {100 * c['ci95'][0]:.1f}–{100 * c['ci95'][1]:.1f}%)"
    L = ["", "## Addendum 1 (EXPLORATORY: added after seeing the main results; not pre-registered; not in the Holm family)", "",
         "| id | kind | sentence a report may use | number(s) | source | figure | batch | plan |",
         "|---|---|---|---|---|---|---|---|"]
    bt, src, b2 = A["by_coord_type"], "`analysis/addendum1.py`", f"{batch_id} + {A['explore_batch']}"
    L.append(f"| A1 | EXPLORATORY | With no identity sentence, the leak rate was {r(bt['self'])} with the workers' own model as "
             f"coordinator, {r(bt['other_qwen'])} with a different Qwen3.5 model and {r(bt['other_family'])} with a "
             f"different family. | self / other_qwen / other_family | {src} | fig7 | {b2} | docs/ADDENDUM-1.md |")
    for term, t in A["logit"]["terms"].items():
        name = term.split("T.")[-1].rstrip("]")
        L.append(f"| A1-{name} | EXPLORATORY | Against the own-model coordinator, a {name} coordinator had odds ratio "
                 f"{t['or']:.2f} (95% CI {t['ci95'][0]:.2f}–{t['ci95'][1]:.2f}), p = {t['p']:.3g} "
                 "(logistic, worker fixed effects). | OR, CI, p | " + f"{src} | fig7 | {b2} | docs/ADDENDUM-1.md |")
    for w in ["qwen9", "qwen27", "qwen35a3b"]:
        cells = [(t, A["by_worker_and_coord_type"].get(f"{w}|{t}")) for t in ["self", "other_qwen", "other_family"]]
        txt = "; ".join(f"{t} {r(c)}" for t, c in cells if c)
        L.append(f"| A1-{w} | EXPLORATORY | For {w} workers: {txt}. | per worker | {src} | fig7 | {b2} | docs/ADDENDUM-1.md |")
    for k, f in A.get("fisher_within_worker", {}).items():
        L.append(f"| A1-fisher-{k.replace('|', '-')} | EXPLORATORY | Within {k.split('|')[0]} workers, own-model vs {k.split('_vs_')[1]} coordinator: "
                 f"two-sided Fisher exact p = {f['p']:.3g} (table {f['table']}). | p | {src} | fig7 | {b2} | docs/ADDENDUM-1.md |")
    return L


def render(R: dict | None, batch_id: str, reason: str | None = None) -> str:
    L = ["# CLAIMS.md: claim ledger", "",
         "Generated by `analysis/claims.py` (do not edit by hand). Each sentence is a neutral lookup for the report, "
         "with numbers from `analysis/results/<batch_id>/results.json`. Figures are in `figures/<batch_id>/`. "
         "Rows marked EXPLORATORY were not pre-registered. Qualitative material is in `docs/OBSERVATIONS.md` "
         "(observations, not results).", ""]
    if R is None:
        L += [f"**Status: {PENDING}.** {reason or ''}", ""]
    else:
        L += [f"**Status:** complete batch `{batch_id}`, PREREG sha256 `{R['prereg_sha256']}`, generated {R['generated_utc']}.", ""]
    L += ["| id | kind | sentence a report may use | number(s) | source | figure | batch | PREREG |",
          "|---|---|---|---|---|---|---|---|"]
    for cid, kind, sec, fig, src, build in claim_specs():
        if R is None:
            sent, nums = PENDING, PENDING
        else:
            sent, nums = build(R)
        L.append(f"| {cid} | {esc(kind)} | {esc(sent)} | {esc(nums)} | `{src}` | {fig} | {batch_id if R else PENDING} | {sec} |")
    if R is not None:
        L += addendum_rows(batch_id)
        L += ["", "## Analysis-plan clarifications applied (analysis/primary.py docstring)"]
        L += [f"- {c}" for c in R["analysis_plan_clarifications"]]
    return "\n".join(L) + "\n"


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("batch", help="runs/<main_batch>")
    a = ap.parse_args(argv)
    R, reason, batch_id = None, None, None
    try:
        info = check_batch(a.batch, expected_kind="main", allow_partial=False)
        batch_id = info.batch_id
        rp = results_dir(info.batch_id) / "results.json"
        R = json.loads(rp.read_text()) if rp.exists() else None
        if R is None:
            reason = "results.json missing; run analysis.primary."
        elif R.get("partial") or R.get("n_episodes_in_file") != info.n_episodes:
            R, reason = None, "results.json is PARTIAL or stale; re-run analysis.primary on the complete batch."
    except BatchRefused as e:
        import re
        reason = re.sub(r" \(\d+ episodes so far\)", "", str(e))  # no partial numbers in the ledger
    OUT.write_text(render(R, batch_id or PENDING, reason))
    print(f"CLAIMS.md written ({'complete' if R else PENDING}: {reason or batch_id})")


if __name__ == "__main__":
    main()
