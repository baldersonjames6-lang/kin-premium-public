"""Pre-registered analysis of the kin-premium swarm batches (PREREG.md v2.1, §5-§7 and §9).

Run everything for one batch with:

    python -m analysis.run_all runs/<batch_id>            # refuses unless main + complete + PREREG sha matches
    python -m analysis.run_all runs/<batch_id> --allow-partial   # development only; outputs stamped PARTIAL
"""
