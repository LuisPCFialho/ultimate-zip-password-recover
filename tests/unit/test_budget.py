from __future__ import annotations

from uzpr.core.budget import BudgetAllocator


def test_free_tier_stages_get_inf() -> None:
    alloc = BudgetAllocator(3600.0)
    budgets = alloc.allocate([1, 2, 3, 4, 5, 13])
    assert budgets[1] == float("inf")
    assert budgets[2] == float("inf")
    assert budgets[3] == float("inf")
    assert budgets[13] == float("inf")


def test_paid_stages_share_pool() -> None:
    alloc = BudgetAllocator(3600.0)
    budgets = alloc.allocate([4, 5, 6, 7, 8, 9, 10, 11, 12])
    total = sum(budgets.values())
    assert abs(total - 3600.0) < 1.0  # full pool distributed


def test_mark_exhausted_redistributes() -> None:
    alloc = BudgetAllocator(3600.0)
    alloc.allocate([4, 5])
    alloc.mark_exhausted(4, 600.0)  # stage 4 returned 600s unused
    new_budgets = alloc.allocate([5])
    # Stage 5 should now have more than its original share
    original_budgets = BudgetAllocator(3600.0).allocate([4, 5])
    assert new_budgets[5] > original_budgets[5]
