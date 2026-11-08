"""Small, tested statistics helpers used by primary.py (PREREG §6).

- ``wilson``: Wilson score interval for a proportion (PREREG §6, "raw rates with Wilson CIs").
- ``group_logit``: ``leak ~ C(group, Treatment(ref)) + C(worker)`` by maximum likelihood (statsmodels), odds
  ratios with Wald 95% CIs and two-sided p-values.
- ``cmh_fallback``: Cochran-Mantel-Haenszel test stratified by worker, used only when the group term is
  separated (a group with 0% or 100% leaks), where the logistic MLE does not exist.
- ``mcnemar_exact``: exact McNemar test on paired flags (PREREG §6, H4).
- ``holm``: Holm step-down adjustment (PREREG §6, across H1-H4).
- ``auroc``: area under the ROC curve with a percentile bootstrap CI.
"""
from __future__ import annotations

import math
import warnings

import numpy as np
import pandas as pd
from scipy.stats import norm


def wilson(k: int, n: int, alpha: float = 0.05) -> tuple[float | None, float | None, float | None]:
    """(rate, low, high) for k successes out of n; (None, None, None) if n == 0."""
    if n == 0:
        return None, None, None
    z = norm.ppf(1 - alpha / 2)
    p = k / n
    denom = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / denom
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / denom
    # clamp: at k = 0 or k = n the bound equals the rate up to rounding (e.g. 0.9999999999999999)
    return float(p), float(min(p, max(0.0, centre - half))), float(max(p, min(1.0, centre + half)))


def rate_obj(series: pd.Series, source: str) -> dict:
    s = series.dropna().astype(bool)
    k, n = int(s.sum()), int(len(s))
    p, lo, hi = wilson(k, n)
    return {"k": k, "n": n, "rate": p, "ci_low": lo, "ci_high": hi, "ci_method": "Wilson 95%", "source": source}


def holm(pvals: dict[str, float], alpha: float = 0.05) -> dict[str, dict]:
    """Holm step-down: sort ascending, adjusted p_(i) = max_{j<=i} min(1, (m-j+1) p_(j))."""
    items = sorted(pvals.items(), key=lambda kv: kv[1])
    m = len(items)
    out, running = {}, 0.0
    for rank, (name, p) in enumerate(items, start=1):
        running = max(running, min(1.0, (m - rank + 1) * p))
        out[name] = {"p_raw": p, "rank": rank, "p_holm": running, "reject_at_0.05": running < alpha}
    # Holm's stopping rule: once one hypothesis is retained, all later ones are retained (implied by max()).
    return out


def mcnemar_exact(b: int, c: int) -> float:
    """Two-sided exact McNemar p for discordant counts b and c (binomial, p = 0.5)."""
    from scipy.stats import binomtest
    n = b + c
    if n == 0:
        return 1.0
    return float(binomtest(min(b, c), n, 0.5, alternative="two-sided").pvalue)


def auroc(labels, scores, n_boot: int = 2000, seed: int = 20261106) -> dict:
    from sklearn.metrics import roc_auc_score
    y = np.asarray(labels, dtype=int)
    s = np.asarray(scores, dtype=float)
    out = {"n": int(len(y)), "n_pos": int(y.sum()), "n_neg": int(len(y) - y.sum())}
    if out["n_pos"] == 0 or out["n_neg"] == 0:
        return out | {"auroc": None, "ci_low": None, "ci_high": None, "estimable": False,
                      "reason": "needs both leaking and non-leaking episodes"}
    a = float(roc_auc_score(y, s))
    rng = np.random.default_rng(seed)
    boots = []
    for _ in range(n_boot):
        idx = rng.integers(0, len(y), len(y))
        if 0 < y[idx].sum() < len(idx):
            boots.append(roc_auc_score(y[idx], s[idx]))
    lo, hi = (float(np.percentile(boots, 2.5)), float(np.percentile(boots, 97.5))) if boots else (None, None)
    return out | {"auroc": a, "ci_low": lo, "ci_high": hi, "estimable": True,
                  "ci_method": f"percentile bootstrap, {n_boot} resamples, seed {seed}"}


def _drop_constant_strata(d: pd.DataFrame, outcome: str, stratum: str) -> tuple[pd.DataFrame, list[str]]:
    """Worker strata whose outcome never varies carry no information on the group effect in a model with
    worker fixed effects (their coefficient diverges); dropping them gives the limit of the MLE."""
    const = [w for w, g in d.groupby(stratum) if g[outcome].nunique() < 2]
    return d[~d[stratum].isin(const)], const


def group_logit(df: pd.DataFrame, outcome: str, ref: str, contrasts: list[str],
                stratum: str = "worker") -> dict[str, dict]:
    """Fit ``outcome ~ C(group, Treatment(ref)) + C(worker)``; return per-contrast OR, CI, p.

    Each returned dict has ``estimable``; when False, ``reason`` says why and the CMH fallback is attached.
    """
    import statsmodels.formula.api as smf

    d = df[["group", stratum, outcome]].dropna().copy()
    d[outcome] = d[outcome].astype(int)
    d, dropped = _drop_constant_strata(d, outcome, stratum)
    res = {}
    base = {"dropped_constant_strata": dropped, "n_model": int(len(d))}
    present = set(d["group"])
    if ref not in present or d[outcome].nunique() < 2:
        for g in contrasts:
            res[g] = base | {"estimable": False, "reason": "outcome constant or reference group absent"}
        return res
    sep = {g for g in present if d.loc[d["group"] == g, outcome].nunique() < 2}
    formula = f"{outcome} ~ C(group, Treatment('{ref}'))" + (f" + C({stratum})" if d[stratum].nunique() > 1 else "")
    caught = []
    fit = None
    if not sep:
        try:
            with warnings.catch_warnings(record=True) as w:
                warnings.simplefilter("always")
                fit = smf.logit(formula, data=d).fit(disp=0, maxiter=200)
                caught = [str(x.message) for x in w]
        except Exception as e:  # singular matrix, separation errors
            caught.append(f"{type(e).__name__}: {e}")
            fit = None
    for g in contrasts:
        r = dict(base, formula=formula, warnings=caught)
        term = f"C(group, Treatment('{ref}'))[T.{g}]"
        if g not in present:
            res[g] = r | {"estimable": False, "reason": f"no episodes in {g}"}
            continue
        if g in sep or ref in sep:
            r |= {"estimable": False, "reason": f"separation: {sorted(sep & {g, ref})} has a constant outcome "
                                                 "in the worker strata kept for the model"}
            r["fallback"] = cmh_fallback(d, outcome, g, ref, stratum)
            res[g] = r
            continue
        if fit is None or term not in fit.params.index or not fit.mle_retvals.get("converged", False) \
                or not np.isfinite(fit.bse[term]) or any("separation" in w.lower() for w in caught):
            r |= {"estimable": False, "reason": "logistic fit failed, did not converge or hit (quasi-)separation"
                                                + (f": {caught[0][:160]}" if caught else "")}
            r["fallback"] = cmh_fallback(d, outcome, g, ref, stratum)
            res[g] = r
            continue
        b, se = float(fit.params[term]), float(fit.bse[term])
        r |= {"estimable": True, "log_or": b, "se": se, "odds_ratio": math.exp(b),
              "ci_low": math.exp(b - 1.959963984540054 * se), "ci_high": math.exp(b + 1.959963984540054 * se),
              "p": float(fit.pvalues[term]), "test": "Wald z, two-sided"}
        res[g] = r
    return res


def cmh_fallback(d: pd.DataFrame, outcome: str, g: str, ref: str, stratum: str = "worker") -> dict:
    """Cochran-Mantel-Haenszel test of group g vs ref stratified by worker (pre-specified fallback)."""
    from statsmodels.stats.contingency_tables import StratifiedTable
    tables = []
    for _, s in d[d["group"].isin([g, ref])].groupby(stratum):
        t = np.array([[((s.group == g) & (s[outcome] == 1)).sum(), ((s.group == g) & (s[outcome] == 0)).sum()],
                      [((s.group == ref) & (s[outcome] == 1)).sum(), ((s.group == ref) & (s[outcome] == 0)).sum()]])
        if t[0].sum() > 0 and t[1].sum() > 0:
            tables.append(t.astype(float))
    if not tables:
        return {"test": "CMH", "estimable": False, "reason": "no stratum has both groups"}
    with np.errstate(divide="ignore", invalid="ignore"), warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)
        st = StratifiedTable(tables)
        tr = st.test_null_odds(correction=True)
        try:
            lo, hi = st.oddsratio_pooled_confint()
        except Exception:
            lo, hi = None, None
        or_ = float(st.oddsratio_pooled)
    fin = lambda x: None if x is None or not np.isfinite(x) else float(x)
    return {"test": "Cochran-Mantel-Haenszel (continuity-corrected), stratified by worker", "estimable": True,
            "p": float(tr.pvalue), "mh_odds_ratio": fin(or_), "ci_low": fin(lo), "ci_high": fin(hi),
            "n_strata": len(tables)}
