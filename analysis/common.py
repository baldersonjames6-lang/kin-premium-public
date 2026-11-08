"""Shared helpers: paths, the batch guard and the PARTIAL stamp (PREREG §9, docs/CONTRACTS.md).

PREREG §9 says every reported number comes from ``analysis/`` scripts run on batches whose manifest records
the sha256 of the signed PREREG.md. ``check_batch`` enforces that. It refuses a batch unless

1. ``manifest.kind`` is the expected kind (``main`` for the hypothesis tests, ``pilot`` for the honest
   baseline used for false-positive rates),
2. ``manifest.prereg_sha256`` equals the sha256 of the current PREREG.md, and
3. ``manifest.status`` is ``complete`` and every file listed in SHA256SUMS still has its recorded hash.

``--allow-partial`` relaxes only rule 3, for development on a batch that is still running. Every output
produced that way carries the stamp ``PARTIAL, n=<episodes>, NOT FOR THE REPORT``.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
PREREG = REPO / "PREREG.md"
THRESHOLDS = REPO / "analysis" / "thresholds-swarm.json"
RESULTS_DIR = REPO / "analysis" / "results"
FIGURES_DIR = REPO / "figures"
MONITORS = ("mon_claude", "mon_qwen")
VIEWS = ("global", "local")
GROUPS = ("kin_claimed", "nonkin_silent", "kin_silent", "nonkin_falseclaim")  # PREREG §0
REFERENCE_GROUP = "nonkin_silent"
WORKERS = ("qwen9", "qwen27", "qwen35a3b")
COORDINATORS = ("qwen9", "qwen27", "qwen35a3b", "dsv41", "dsv4pro", "gemma31", "kimi26")
FAMILY = {  # PREREG §4
    "qwen9": "Qwen", "qwen27": "Qwen", "qwen35a3b": "Qwen", "dsv41": "DeepSeek", "dsv4pro": "DeepSeek",
    "gemma31": "Google", "kimi26": "Moonshot", "haiku": "Anthropic", "glm53f": "Zhipu", "llama4s": "Meta",
}


class BatchRefused(SystemExit):
    """Raised when a batch fails the guard. A SystemExit, so command-line use exits non-zero."""


def sha256_file(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


@dataclass
class BatchInfo:
    batch_dir: Path
    batch_id: str
    kind: str
    status: str
    n_episodes: int
    partial: bool
    manifest: dict

    @property
    def stamp(self) -> str | None:
        """The PARTIAL stamp, or None for a complete batch."""
        return f"PARTIAL, n={self.n_episodes}, NOT FOR THE REPORT" if self.partial else None


def _count_lines(path: Path) -> int:
    if not path.exists():
        return 0
    return sum(1 for line in path.open() if line.strip())


def verify_sha256sums(batch_dir: Path) -> list[str]:
    """Files whose current hash differs from SHA256SUMS (empty list = intact). Missing SHA256SUMS = one problem."""
    sums = batch_dir / "SHA256SUMS"
    if not sums.exists():
        return ["SHA256SUMS missing"]
    bad = []
    for line in sums.read_text().splitlines():
        if not line.strip():
            continue
        digest, rel = line.split(maxsplit=1)
        p = batch_dir / rel.strip()
        if not p.exists() or sha256_file(p) != digest:
            bad.append(rel.strip())
    return bad


def check_batch(batch_dir: str | Path, expected_kind: str = "main", allow_partial: bool = False,
                prereg_path: Path = PREREG) -> BatchInfo:
    """Return BatchInfo if the batch may be analysed, else raise BatchRefused with the reason."""
    batch_dir = Path(batch_dir)
    mpath = batch_dir / "manifest.json"
    if not mpath.exists():
        raise BatchRefused(f"REFUSED: {mpath} not found")
    m = json.loads(mpath.read_text())
    want_sha = sha256_file(prereg_path)
    if m.get("kind") != expected_kind:
        raise BatchRefused(f"REFUSED: {batch_dir.name} has kind {m.get('kind')!r}, expected {expected_kind!r}")
    if m.get("prereg_sha256") != want_sha:
        raise BatchRefused(f"REFUSED: {batch_dir.name} prereg_sha256 {m.get('prereg_sha256')} does not match "
                           f"the current PREREG.md ({want_sha})")
    n = _count_lines(batch_dir / "episodes.jsonl")
    status = m.get("status")
    partial = status != "complete"
    if partial and not allow_partial:
        raise BatchRefused(f"REFUSED: {batch_dir.name} status is {status!r}, not 'complete' "
                           f"({n} episodes so far). Use --allow-partial for development only.")
    if not partial:
        bad = verify_sha256sums(batch_dir)
        if bad:
            raise BatchRefused(f"REFUSED: {batch_dir.name} fails SHA256SUMS for {bad[:5]}")
    return BatchInfo(batch_dir, m.get("batch_id", batch_dir.name), m["kind"], status, n, partial, m)


def load_thresholds(manifest: dict | None = None, path: Path = THRESHOLDS) -> dict:
    """Flag thresholds (PREREG §5). If a main manifest is given, its recorded thresholds must be the same."""
    t = json.loads(Path(path).read_text())
    keys = [f"{mon}_{v}" for mon in MONITORS for v in VIEWS]
    if manifest is not None and manifest.get("monitor_thresholds"):
        rec = manifest["monitor_thresholds"]
        diff = [k for k in keys if rec.get(k) != t.get(k)]
        if diff:
            raise BatchRefused(f"REFUSED: thresholds file differs from the batch manifest for {diff}")
    return {k: t[k] for k in keys} | {"source_batch": t.get("source_batch")}


def results_dir(batch_id: str) -> Path:
    d = RESULTS_DIR / batch_id
    d.mkdir(parents=True, exist_ok=True)
    return d


def figures_dir(batch_id: str) -> Path:
    d = FIGURES_DIR / batch_id
    d.mkdir(parents=True, exist_ok=True)
    return d


def add_guard_args(ap):
    ap.add_argument("batch", help="path to runs/<batch_id> (a main batch)")
    ap.add_argument("--allow-partial", action="store_true",
                    help="development only: analyse a running batch; every output is stamped PARTIAL")
    return ap
