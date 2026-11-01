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


def words_from_pdf(path: str | Path, page_index: int, *, apply_rotation: bool = True) -> list[Word]:
    """Extract positioned words from one page. ``page_index`` is 0-based.

    **Rotation matters.** Several sheets in the structural set are plotted with ``/Rotate 270``
    (ST-02 among them). PyMuPDF reports word coordinates in *unrotated* page space, so on
    those sheets a visual row arrives as a column and the title block lands on the left edge.
    By default the page's rotation matrix is applied, putting every word where it appears on
    the rendered page -- which is also what a stored ``bbox`` must mean for an engineer
    checking the citation.

    Pass ``apply_rotation=False`` for raw PDF-space coordinates.

    Deliberately thin: all logic lives in rows.py / viewport.py so it can be tested against
    stored fixtures without carrying client drawings in the repository.
    """
    import pymupdf

    with pymupdf.open(path) as doc:
        if not 0 <= page_index < len(doc):
            raise IndexError(f"page_index {page_index} out of range for {path} ({len(doc)} pages)")
        page = doc[page_index]
        raw = page.get_text("words")

        if not apply_rotation or not page.rotation:
            return [Word(x=x0, y=y0, text=t, x1=x1, y1=y1) for x0, y0, x1, y1, t, *_ in raw]

        matrix = page.rotation_matrix
        out: list[Word] = []
        for x0, y0, x1, y1, text, *_ in raw:
            box = pymupdf.Rect(x0, y0, x1, y1) * matrix
            out.append(Word(x=box.x0, y=box.y0, text=text, x1=box.x1, y1=box.y1))
        return out


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
