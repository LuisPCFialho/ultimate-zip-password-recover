from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from uzpr.core.capability import CapabilityProbe
from uzpr.core.orchestrator import Orchestrator
from uzpr.core.stages.protocol import Stage
from uzpr.engines.tool_manager import ToolNotFoundError, find_tool
from uzpr.persistence.repo import SessionRepo
from uzpr.util.logging import configure, get_logger
from uzpr.util.paths import db_path, logs_dir, tools_dir

log = get_logger(__name__)


@dataclass(slots=True)
class AppState:
    orchestrator: Orchestrator
    repo: SessionRepo
    capability: CapabilityProbe


def build_application() -> AppState:
    """Construct and wire together the full application graph."""

    # Configure structured logging first so everything below can emit logs.
    configure(log_dir=logs_dir(), level="INFO")

    # --- Persistence ---
    repo = SessionRepo(db_path=db_path(), dpapi_key=b"")

    # --- External tool discovery ---
    hashcat_binary: Path | None = None
    try:
        hashcat_binary = find_tool("hashcat")
        log.info("tool_found", tool="hashcat", path=str(hashcat_binary))
    except ToolNotFoundError:
        log.warning("tool_not_found", tool="hashcat")

    john_binary: Path | None = None
    try:
        john_binary = find_tool("john")
        log.info("tool_found", tool="john", path=str(john_binary))
    except ToolNotFoundError:
        log.warning("tool_not_found", tool="john")

    bkcrack_binary: Path | None = None
    try:
        bkcrack_binary = find_tool("bkcrack")
        log.info("tool_found", tool="bkcrack", path=str(bkcrack_binary))
    except ToolNotFoundError:
        log.warning("tool_not_found", tool="bkcrack")

    # --- Capability probe ---
    probe = CapabilityProbe(db_path=db_path(), hashcat_binary=hashcat_binary)

    # --- Engine runners ---
    _work_dir = tools_dir()

    hashcat_runner = None
    if hashcat_binary is not None:
        from uzpr.engines.hashcat import HashcatRunner

        hashcat_runner = HashcatRunner(hashcat_binary, work_dir=_work_dir)

    john_runner = None
    if john_binary is not None:
        from uzpr.engines.john import JohnRunner

        john_runner = JohnRunner(john_binary, work_dir=_work_dir)

    bkcrack_runner = None
    if bkcrack_binary is not None:
        from uzpr.engines.bkcrack import BkcrackRunner

        bkcrack_runner = BkcrackRunner(bkcrack_binary, work_dir=_work_dir)

    # --- Stage instantiation (ordered 1..13) ---
    from uzpr.core.stages.s01_known_password import KnownPasswordStage
    from uzpr.core.stages.s02_partial_mask import PartialMaskStage
    from uzpr.core.stages.s03_smart_wordlist import SmartWordlistStage

    # Stages 4–13 are imported individually so that ImportError for any single
    # stage does not prevent the others from loading.  Each falls back to None
    # and is omitted from the tuple when its module is not yet present.

    def _try_import(module: str, cls: str) -> type[Stage] | None:
        try:
            import importlib

            mod = importlib.import_module(module)
            return getattr(mod, cls)  # type: ignore[return-value]
        except (ImportError, AttributeError) as exc:
            log.debug("stage_module_unavailable", module=module, cls=cls, reason=str(exc))
            return None

    S04 = _try_import("uzpr.core.stages.s04_top_passwords", "TopPasswordsStage")
    S05 = _try_import("uzpr.core.stages.s05_dictionary", "DictionaryStage")
    S06 = _try_import("uzpr.core.stages.s06_john_rules", "JohnRulesStage")
    S07 = _try_import("uzpr.core.stages.s07_hashcat_rules", "HashcatRulesStage")
    S08 = _try_import("uzpr.core.stages.s08_mask_attack", "MaskAttackStage")
    S09 = _try_import("uzpr.core.stages.s09_hybrid", "HybridStage")
    S10 = _try_import("uzpr.core.stages.s10_prince", "PrinceStage")
    S11 = _try_import("uzpr.core.stages.s11_markov", "MarkovStage")
    S12 = _try_import("uzpr.core.stages.s12_bruteforce", "BruteForceStage")
    S14 = _try_import("uzpr.core.stages.s14_combinator", "CombinatorStage")
    S13 = _try_import("uzpr.core.stages.s13_bkcrack", "BkcrackStage")

    # Build stage instances.  Stages that accept runner instances receive them
    # via keyword argument; stages that don't need them take no args.
    # If a runner is None the stage is still instantiated — it is expected to
    # return a zero-prior StagePlan (SKIPPED signal) from prepare().
    all_stages: list[Stage] = [
        KnownPasswordStage(),
        PartialMaskStage(),
        SmartWordlistStage(),
    ]

    def _maybe_add(cls: type[Stage] | None, **kwargs: object) -> None:
        if cls is None:
            return
        try:
            # Pass runner kwargs only when the constructor accepts them.
            import inspect

            sig = inspect.signature(cls.__init__)
            accepted = set(sig.parameters.keys()) - {"self"}
            filtered = {k: v for k, v in kwargs.items() if k in accepted}
            all_stages.append(cls(**filtered))  # type: ignore[call-arg]
        except Exception as exc:
            log.warning("stage_instantiation_failed", stage=cls.__name__, error=str(exc))

    _maybe_add(S04, hashcat_runner=hashcat_runner)
    _maybe_add(S05, hashcat_runner=hashcat_runner, john_runner=john_runner)
    _maybe_add(S06, john_runner=john_runner)
    _maybe_add(S07, hashcat_runner=hashcat_runner)
    _maybe_add(S08, hashcat_runner=hashcat_runner)
    _maybe_add(S09, hashcat_runner=hashcat_runner)
    _maybe_add(S10, hashcat_runner=hashcat_runner)
    _maybe_add(S11, hashcat_runner=hashcat_runner)
    _maybe_add(S12, hashcat_runner=hashcat_runner)
    _maybe_add(S14, hashcat_runner=hashcat_runner)
    _maybe_add(S13, bkcrack_runner=bkcrack_runner)

    log.info("application_built", stage_count=len(all_stages))

    orchestrator = Orchestrator(
        repo=repo,
        capability=probe,
        stages=tuple(all_stages),
    )
    return AppState(orchestrator=orchestrator, repo=repo, capability=probe)
