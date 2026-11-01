"""Positional word extraction.

The foundation of every extractor in this project. See docs/template-analysis.md section 4:
these sheets are AutoCAD plots, so the PDF text layer is emitted in draw order, not layout
order. Nothing downstream may use reading order. Everything starts from words plus coordinates.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class Word:
    """A single text token with its position on the page.

    Coordinates are PDF points, origin top-left (PyMuPDF convention): y increases downward.
    """

    x: float
    y: float
    text: str
    x1: float | None = None
    y1: float | None = None

    @property
    def width(self) -> float | None:
        return None if self.x1 is None else self.x1 - self.x


def words_from_pdf(path: str | Path, page_index: int) -> list[Word]:
    """Extract positioned words from one page. ``page_index`` is 0-based.

    Deliberately thin: all logic lives in rows.py / viewport.py so it can be tested against
    stored fixtures without carrying client drawings in the repository.
    """
    import fitz  # imported lazily so fixture-based tests do not require PyMuPDF

    with fitz.open(path) as doc:
        if not 0 <= page_index < len(doc):
            raise IndexError(f"page_index {page_index} out of range for {path} ({len(doc)} pages)")
        page = doc[page_index]
        return [
            Word(x=x0, y=y0, text=text, x1=x1, y1=y1)
            for x0, y0, x1, y1, text, *_ in page.get_text("words")
        ]


def load_words(path: str | Path) -> list[Word]:
    """Load a word fixture written by :func:`dump_words`."""
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    return [
        Word(x=w["x"], y=w["y"], text=w["text"], x1=w.get("x1"), y1=w.get("y1"))
        for w in payload["words"]
    ]


def dump_words(words: list[Word], path: str | Path, **meta: object) -> None:
    """Write a word fixture, preserving provenance metadata alongside the words."""
    payload = {
        **meta,
        "words": [
            {
                k: v
                for k, v in (("x", w.x), ("y", w.y), ("text", w.text), ("x1", w.x1), ("y1", w.y1))
                if v is not None
            }
            for w in words
        ],
    }
    Path(path).write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
