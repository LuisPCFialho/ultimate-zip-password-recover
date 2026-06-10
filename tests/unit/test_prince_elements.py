from __future__ import annotations

from pathlib import Path

from uzpr.wordlist.prince import build_prince_elements


def _write_top_dict(tmp_path: Path, n: int) -> Path:
    top = tmp_path / "top.txt"
    top.write_text("\n".join(f"word{i:03d}" for i in range(n)) + "\n", encoding="utf-8")
    return top


def test_build_prince_elements_empty_stems(tmp_path: Path) -> None:
    top = _write_top_dict(tmp_path, 50)
    out = tmp_path / "elements.txt"

    build_prince_elements([], top, out)

    lines = [line for line in out.read_text(encoding="utf-8").splitlines() if line]
    # Unhinted run pulls up to 500 from top_dict; we only have 50 in the source.
    assert len(lines) == 50
    assert lines[0] == "word000"


def test_build_prince_elements_with_extra_words(tmp_path: Path) -> None:
    top = _write_top_dict(tmp_path, 10)
    out = tmp_path / "elements.txt"

    build_prince_elements([], top, out, extra_words=["alpha", "beta", "alpha"])

    lines = [line for line in out.read_text(encoding="utf-8").splitlines() if line]
    # alpha + beta (dedup) + 10 from top_dict
    assert lines[0] == "alpha"
    assert lines[1] == "beta"
    assert len(lines) == 12


def test_build_prince_elements_hinted(tmp_path: Path) -> None:
    top = _write_top_dict(tmp_path, 1500)
    out = tmp_path / "elements.txt"

    build_prince_elements(["myname", "mypet"], top, out)

    lines = [line for line in out.read_text(encoding="utf-8").splitlines() if line]
    assert lines[0] == "myname"
    assert lines[1] == "mypet"
    # 2 stems + 1000 from top_dict
    assert len(lines) == 1002
