from __future__ import annotations

STAGE_PRIORS: dict[int, float] = {
    1: 1.0, 2: 0.8, 3: 0.4,  # oracle / free tier
    4: 0.18, 5: 0.20, 6: 0.12, 7: 0.15,
    8: 0.10, 9: 0.08, 10: 0.06, 11: 0.05, 12: 0.50,
    13: 1.0,  # oracle / free tier
}

FREE_TIER_STAGES: frozenset[int] = frozenset({1, 2, 3, 13})  # no budget cap


class BudgetAllocator:
    """Greedy EV allocator that distributes a paid-time pool proportionally
    by per-stage prior probabilities, with free-tier stages uncapped."""

    def __init__(
        self,
        total_budget_s: float,
        stage_priors: dict[int, float] | None = None,
    ) -> None:
        self._paid_pool: float = total_budget_s
        self._priors: dict[int, float] = stage_priors if stage_priors is not None else STAGE_PRIORS

    def allocate(self, remaining_stages: list[int]) -> dict[int, float]:
        """Return a budget (seconds) for each stage in *remaining_stages*.

        Free-tier stages (1, 2, 3, 13) receive ``float('inf')``.
        Paid stages share the remaining paid pool in proportion to their prior.
        """
        result: dict[int, float] = {}

        remaining_paid = [s for s in remaining_stages if s not in FREE_TIER_STAGES]
        paid_weight_sum = sum(self._priors.get(s, 0.0) for s in remaining_paid)

        for stage_no in remaining_stages:
            if stage_no in FREE_TIER_STAGES:
                result[stage_no] = float("inf")
            else:
                prior = self._priors.get(stage_no, 0.0)
                if paid_weight_sum > 0.0:
                    result[stage_no] = self._paid_pool * prior / paid_weight_sum
                else:
                    result[stage_no] = 0.0

        return result

    def mark_exhausted(self, stage_no: int, unused_s: float) -> None:
        """Return *unused_s* seconds back to the paid pool for redistribution."""
        if stage_no not in FREE_TIER_STAGES and unused_s > 0.0:
            self._paid_pool += unused_s

    def mark_found(self, stage_no: int) -> None:
        """No-op — session ends immediately when a password is found."""
        pass
