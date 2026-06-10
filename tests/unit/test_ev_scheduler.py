"""Tests for the EV (expected-value) scheduler ordering in the orchestrator."""

from __future__ import annotations

from dataclasses import dataclass

import pytest

from uzpr.core.orchestrator import _sort_by_ev, _yield_density
from uzpr.core.stages.protocol import StagePlan


@dataclass
class _FakeStage:
    stage_no: int
    name: str = "fake"
    engine: str = "native"


def _plan(keyspace: int, cps: float, prior: float, *, requires_gpu: bool = False) -> StagePlan:
    return StagePlan(
        estimated_keyspace=keyspace,
        estimated_candidates_per_sec=cps,
        prior_probability=prior,
        requires_gpu=requires_gpu,
        can_resume=False,
    )


@pytest.mark.unit
def test_yield_density_matches_spec_values() -> None:
    # A: keyspace=10, cps=100, prior=0.5 → expected_seconds=0.1, density=5.0
    assert _yield_density(_plan(10, 100, 0.5)) == pytest.approx(5.0)
    # B: keyspace=1000, cps=100, prior=0.9 → expected_seconds=10, density=0.09
    assert _yield_density(_plan(1000, 100, 0.9)) == pytest.approx(0.09)
    # C: keyspace=100, cps=100, prior=0.3 → expected_seconds=1, density=0.3
    assert _yield_density(_plan(100, 100, 0.3)) == pytest.approx(0.3)


@pytest.mark.unit
def test_sort_by_ev_orders_by_descending_density() -> None:
    a = _FakeStage(stage_no=1)
    b = _FakeStage(stage_no=2)
    c = _FakeStage(stage_no=3)
    prepared = {
        1: _plan(10, 100, 0.5),     # density 5.0
        2: _plan(1000, 100, 0.9),   # density 0.09
        3: _plan(100, 100, 0.3),    # density 0.3
    }
    ordered = _sort_by_ev(prepared, (a, b, c), gpu_available=True)
    assert [s.stage_no for s in ordered] == [1, 3, 2]


@pytest.mark.unit
def test_sort_by_ev_excludes_stages_not_in_prepared() -> None:
    a = _FakeStage(stage_no=1)
    b = _FakeStage(stage_no=2)
    # Only stage 1 is prepared (stage 2 has zero prior → filtered out).
    prepared = {1: _plan(10, 100, 0.5)}
    ordered = _sort_by_ev(prepared, (a, b), gpu_available=True)
    assert [s.stage_no for s in ordered] == [1]


@pytest.mark.unit
def test_sort_by_ev_deprioritizes_gpu_stages_when_no_gpu() -> None:
    cpu_stage = _FakeStage(stage_no=1)
    gpu_stage = _FakeStage(stage_no=2)
    # GPU stage has higher density but no GPU is available → must run last.
    prepared = {
        1: _plan(1000, 100, 0.1),                       # density 0.01
        2: _plan(10, 100, 0.9, requires_gpu=True),      # density 9.0
    }
    ordered = _sort_by_ev(prepared, (cpu_stage, gpu_stage), gpu_available=False)
    assert [s.stage_no for s in ordered] == [1, 2]


@pytest.mark.unit
def test_sort_by_ev_keeps_gpu_stages_first_when_gpu_available() -> None:
    cpu_stage = _FakeStage(stage_no=1)
    gpu_stage = _FakeStage(stage_no=2)
    prepared = {
        1: _plan(1000, 100, 0.1),                       # density 0.01
        2: _plan(10, 100, 0.9, requires_gpu=True),      # density 9.0
    }
    ordered = _sort_by_ev(prepared, (cpu_stage, gpu_stage), gpu_available=True)
    assert [s.stage_no for s in ordered] == [2, 1]


@pytest.mark.unit
def test_sort_by_ev_empty_returns_empty() -> None:
    assert _sort_by_ev({}, (), gpu_available=True) == []
    assert _sort_by_ev({}, (_FakeStage(stage_no=1),), gpu_available=True) == []
