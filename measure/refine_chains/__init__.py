"""refine_chains — the composed-drift census RULINGS.md D4 ordered.

holo3 refines a window again whenever its certified reach outgrows the
basis of its last revision, so the revisions COMPOSE.  The D4 ruling
kept that chain, added the already-stood guard, and ordered this
measurement before anyone makes chains cheaper or longer: how long the
chains actually are on the archived material, how far a chained window
has travelled from the placement it was accepted at, and whether
chained windows are the ones that lose tiles.

Reads the archived event streams and fact snapshots only.  No decode,
no receiver run, nothing outside this worktree is written.

    PYTHONPATH=src:. <python> -m measure.refine_chains.census
    PYTHONPATH=src:. <python> -m measure.refine_chains.census --run sheet-I

See ``README.md`` beside this file.
"""
