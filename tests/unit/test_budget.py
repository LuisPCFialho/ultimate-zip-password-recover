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


def test_consume_shrinks_pool() -> None:
    alloc = BudgetAllocator(3600.0)
    # Baseline grant for stages [5, 6] from the full pool.
    original_budgets = alloc.allocate([5, 6])
    alloc.consume(4, 600.0)  # stage 4 consumed 600s, draining the pool
    # Re-allocating the SAME remaining stages now grants LESS, because the
    # pool shrank — consuming time never inflates later budgets.
    new_budgets = alloc.allocate([5, 6])
    assert new_budgets[5] < original_budgets[5]
    assert new_budgets[6] < original_budgets[6]
    # The pool is now 3600 - 600 = 3000, shared by [5, 6].
    assert abs(sum(new_budgets.values()) - 3000.0) < 1e-6


def test_consume_free_tier_is_noop() -> None:
    alloc = BudgetAllocator(1000.0)
    alloc.consume(1, 500.0)  # free-tier stage — must not draw the paid pool
    budgets = alloc.allocate([4])
    assert abs(budgets[4] - 1000.0) < 1e-6


def test_total_grants_never_exceed_budget() -> None:
    alloc = BudgetAllocator(1000.0)
    remaining = [4, 5, 6, 7, 8, 9, 10, 11, 12]
    granted_total = 0.0
    for stage in list(remaining):
        budgets = alloc.allocate(remaining)
        grant = budgets[stage]
        granted_total += grant
        # Worst case: each stage uses its full grant.
        alloc.consume(stage, grant)
        remaining = [n for n in remaining if n != stage]

    # Invariant: total paid grants never exceed the session budget.
    assert granted_total <= 1000.0 + 1e-6

    # Once the pool is drained, further paid stages get ~0.
    drained = BudgetAllocator(1000.0)
    drained.consume(12, 1000.0)
    assert abs(drained.allocate([4])[4]) < 1e-6
