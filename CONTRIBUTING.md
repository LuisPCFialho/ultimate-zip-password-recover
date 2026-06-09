# Contributing

Thank you for considering a contribution. This project aims for a small, focused codebase with high test coverage and strict type safety.

## Development setup

```powershell
git clone https://github.com/LuisPCFialho/ultimate-zip-password-recover.git
cd "ultimate-zip-password-recover"
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -e ".[dev]"
pre-commit install
```

## Standards

- **Type checking** — `pyright --strict` must pass before a PR is merged.
- **Linting** — `ruff check` and `black --check` must pass.
- **Tests** — every new attack module needs unit tests with synthetic archives. Coverage target: 80%.
- **Commits** — Conventional Commits format (`feat:`, `fix:`, `docs:`, `chore:`, `refactor:`, `test:`, `perf:`, `ci:`).
- **PRs** — small, focused, with passing CI. Include test plan in the description.

## Architecture

Read [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) before opening a non-trivial PR. The cascading-attack pipeline is the heart of the project — changes there need particular care.

## Adding a new attack stage

1. Create `src/uzpr/core/attacks/<stage_name>.py` implementing the `Stage` protocol from `src/uzpr/core/attack_engine.py`.
2. Register it in `src/uzpr/core/pipeline.py` at the appropriate cascade position.
3. Add a unit test in `tests/unit/attacks/test_<stage_name>.py`.
4. Add an integration test with a known synthetic archive in `tests/integration/`.
5. Update [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) cascade table.

## Adding a new archive format

Beyond ZIP and RAR (the v1 scope), formats like 7z, Office, PDF, and KeePass are tracked in the roadmap. The basic shape is: add `src/uzpr/core/formats/<format>.py`, implement archive detection + hash extraction, and register in `src/uzpr/core/archive_detector.py`.

## Code of conduct

Be kind. Disagreements about technical decisions are welcome; personal attacks are not.
