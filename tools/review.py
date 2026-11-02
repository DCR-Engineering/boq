#!/usr/bin/env python3
"""Start the engineer review screen for a project.

    python tools/review.py --drawings ./samples --reviewer "S.Abbas"

Serves on localhost only: the screen shows unreviewed client quantities and has no
authentication.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from boq.extract.architectural import area_schedule
from boq.extract.thermal import thermal_calc
from boq.extract.thermal.workbook import CellMap
from boq.review.app import serve
from boq.review.session import ReviewSession
from boq.rules import engine
from boq.text.words import load_words

FIXTURES = Path(__file__).resolve().parent.parent / "tests" / "fixtures" / "DCR2564"

SET_A_WINDOWS = {
    "W01": 2,
    "W02": 3,
    "W03": 2,
    "W05": 1,
    "W06": 2,
    "W07": 1,
    "W08": 1,
    "W09": 1,
    "W10": 2,
    "W13": 1,
    "W14": 1,
    "W15": 1,
    "W16": 2,
    "W17": 2,
}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--drawings",
        type=Path,
        action="append",
        default=[],
        help="folder holding the project's PDFs (repeatable)",
    )
    ap.add_argument("--reviewer", default="engineer")
    ap.add_argument("--port", type=int, default=8765)
    ap.add_argument("--threshold", type=float, default=0.80)
    args = ap.parse_args()

    payload = json.loads((FIXTURES / "thermal_workbook.cells.json").read_text("utf-8"))
    thermal = thermal_calc.parse(CellMap.from_dict(payload["sheets"]))
    areas = area_schedule.parse(load_words(FIXTURES / "arch_p05_area_schedule.words.json"))

    result = engine.run(
        area_schedule=areas,
        thermal=thermal,
        set_a_window_counts=SET_A_WINDOWS,
        project={"project_no": "DCR2564", "title": "Proposed Two Storey Villa"},
        source_files=[
            {"file": "THERMAL_DCR2564.xlsx", "sha256": "b" * 64, "set": "C", "file_type": "xlsx"}
        ],
    )
    session = ReviewSession(result, threshold=args.threshold)
    print(
        f"{len(session.items)} items, {len(session.queue)} below "
        f"{args.threshold:.0%} confidence, {len(session.export_blockers())} export blockers"
    )
    serve(session, drawings=args.drawings, reviewer=args.reviewer, port=args.port)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
