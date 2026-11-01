#!/usr/bin/env python3
"""Generate anonymised word fixtures from the real drawing sets.

Real client drawings are never committed. What goes into tests/fixtures/ is the extracted
word list for one region of one page, with title-block personal data removed.

Usage:
    python tools/make_fixtures.py --pdf /path/to/STR2564.pdf --page 5 \
        --name str_p05_column_schedule --sheet "ST - 02" [--region x0 y0 x1 y1]

Run with no --region to capture the whole page (minus redacted tokens).
"""

from __future__ import annotations

import argparse
import datetime as _dt
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from boq.text.words import Word, dump_words, words_from_pdf

# Personal and contact data stripped from every fixture. Matching is case-insensitive and by
# token, so a name split across words is caught piece by piece.
REDACT_TOKENS = {
    "balqees",
    "salwa",
    "khalaf",
    "shaikh",
    "mahmood",
    "mohamed",
    "ebrahim",
    "almosawi",
    "marzooq",
    "s.ahmed",
    "s.abbas",
    "iconeng.bh@gmail.com",
}
REDACT_SUBSTRINGS = ("@", "+973", "epp/bn")


def is_redacted(word: Word) -> bool:
    low = word.text.lower()
    return low in REDACT_TOKENS or any(s in low for s in REDACT_SUBSTRINGS)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--pdf", required=True, type=Path)
    ap.add_argument("--page", required=True, type=int, help="1-based page number")
    ap.add_argument("--name", required=True, help="fixture basename")
    ap.add_argument("--sheet", default=None, help="sheet number as printed, e.g. 'ST - 02'")
    ap.add_argument("--region", nargs=4, type=float, metavar=("X0", "Y0", "X1", "Y1"))
    ap.add_argument(
        "--out", type=Path, default=Path("tests/fixtures/DCR2564"), help="output directory"
    )
    args = ap.parse_args()

    if not args.pdf.exists():
        print(f"error: {args.pdf} not found", file=sys.stderr)
        return 1

    words = words_from_pdf(args.pdf, args.page - 1)
    total = len(words)

    if args.region:
        x0, y0, x1, y1 = args.region
        words = [w for w in words if x0 <= w.x <= x1 and y0 <= w.y <= y1]

    kept = [w for w in words if not is_redacted(w)]
    redacted = len(words) - len(kept)

    args.out.mkdir(parents=True, exist_ok=True)
    path = args.out / f"{args.name}.words.json"
    dump_words(
        kept,
        path,
        _provenance={
            "source_file": args.pdf.name,
            "page": args.page,
            "sheet": args.sheet,
            "region": args.region,
            "captured": _dt.date.today().isoformat(),
            "method": "PyMuPDF page.get_text('words')",
            "anonymised": True,
            "words_on_page": total,
            "words_redacted": redacted,
        },
    )
    print(f"wrote {path} ({len(kept)} words, {redacted} redacted, {total} on page)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
