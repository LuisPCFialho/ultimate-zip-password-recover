from __future__ import annotations

from uzpr.archive.signatures import signature_for, usable_signatures


def test_png_signature_usable() -> None:
    sig = signature_for("photo.PNG")
    assert sig is not None
    assert sig.name == "png"
    assert len(sig.magic) == 16


def test_unknown_extension_none() -> None:
    assert signature_for("x.xyz") is None


def test_usable_all_12plus() -> None:
    sigs = usable_signatures()
    assert sigs  # non-empty
    assert all(len(sig.magic) >= 12 for sig in sigs)


def test_pdf_not_usable() -> None:
    pdf = signature_for("report.pdf")
    assert pdf is not None
    assert len(pdf.magic) == 7
    assert pdf not in usable_signatures()


def test_longest_magic_preferred() -> None:
    # PNG (16-byte magic) is usable; a shorter magic like ZIP (4 bytes) is not.
    png = signature_for("image.png")
    zip_sig = signature_for("archive.zip")
    assert png is not None
    assert zip_sig is not None
    assert len(png.magic) > len(zip_sig.magic)
    assert png in usable_signatures()
    assert zip_sig not in usable_signatures()
