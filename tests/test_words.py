"""Word extraction and fixture round-trip tests."""

from __future__ import annotations

import json

import pytest

from boq.text.words import Word, dump_words, load_words, words_from_pdf


def test_width_none_without_x1():
    assert Word(0, 0, "a").width is None


def test_width_from_x1():
    assert Word(10, 0, "a", x1=35).width == 25


def test_dump_load_round_trip(tmp_path):
    words = [Word(1.5, 2.5, "ALPHA", x1=20.0, y1=12.0), Word(30.0, 2.5, "BETA")]
    path = tmp_path / "f.words.json"
    dump_words(words, path, _provenance={"source_file": "x.pdf"})
    assert load_words(path) == words


def test_dump_preserves_provenance(tmp_path):
    path = tmp_path / "f.words.json"
    dump_words([Word(0, 0, "a")], path, _provenance={"source_file": "x.pdf", "page": 5})
    payload = json.loads(path.read_text())
    assert payload["_provenance"]["page"] == 5


def test_dump_is_utf8_clean_for_arabic(tmp_path):
    """Build prompt section 10: the pipeline must not mangle or drop Arabic strings."""
    arabic = "مملكة البحرين"
    path = tmp_path / "ar.words.json"
    dump_words([Word(0, 0, arabic)], path)
    assert load_words(path)[0].text == arabic
    assert arabic in path.read_text(encoding="utf-8")


def test_words_from_pdf_rejects_out_of_range_page(tmp_path):
    fitz = pytest.importorskip("fitz")
    pdf = tmp_path / "one.pdf"
    doc = fitz.open()
    doc.new_page()
    doc.save(pdf)
    doc.close()
    with pytest.raises(IndexError, match="out of range"):
        words_from_pdf(pdf, 5)


def test_words_from_pdf_reads_positions(tmp_path):
    fitz = pytest.importorskip("fitz")
    pdf = tmp_path / "t.pdf"
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((72, 100), "HELLO")
    doc.save(pdf)
    doc.close()

    words = words_from_pdf(pdf, 0)
    assert [w.text for w in words] == ["HELLO"]
    assert words[0].x == pytest.approx(72, abs=2)
    assert words[0].x1 is not None
