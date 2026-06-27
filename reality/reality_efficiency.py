"""V8 Reality Engine efficiency tuning."""

from __future__ import annotations

# World model cap — investigate fewer candidates, eliminate faster
MAX_WORLD_MODELS = 6
MAX_INVESTIGATIONS_STORED = 48

# Cognitive deliberation rounds when Reality Engine is active (1 = faster, 2 = richer)
REALITY_DELIBERATION_ROUNDS = 1

# Strategy scoring — rank top N only (full playbook is ~18 strategies)
STRATEGY_RANK_TOP_N = 5

# Persist reality state once per full symbol batch, not every evaluate()
DEFER_REALITY_STATE_PERSIST = True
