"""Column schedule regression test (Set B, sheet ST-02).

PENDING FIXTURE. The second of the two regression tests promised in
docs/proposed-structure.md section 5. It cannot be written yet: the sample drawing files were
only available in the analysis session, and while that session captured the *text* of this
schedule it did not capture per-word coordinates for it.

Synthesising coordinates here would make the test circular -- it would assert that the
positional reader reproduces positions this file invented, which proves nothing about the real
sheet. The fixture must be generated from STR2564.pdf with tools/make_fixtures.py.

Expected values, read off the sheet and recorded in docs/template-analysis.md section 6.1:

    mark   b     d     vertical   links @ support   links @ midspan
    C1     200   600   12 Y16     2T8 @ 100 c/c     2T8 @ 150 c/c
    C2     200   500    8 Y16     2T8 @ 100 c/c     2T8 @ 200 c/c
    C3     200   300    6 Y12      T8 @ 200 c/c      T8 @ 200 c/c
    C4     300   600   16 Y20     2T10 @ 100 c/c    2T10 @ 150 c/c
    BC     200   400    6 Y16      T8 @ 200 c/c      T8 @ 200 c/c

This schedule is the sharpest test of the positional reader: in document order it arrives as
three disconnected runs (all bar callouts, then all marks, then all dimensions).
"""

import pytest

pytestmark = pytest.mark.skip(
    reason="fixture not yet generated -- needs STR2564.pdf re-uploaded; see module docstring"
)


def test_column_schedule_marks_and_dimensions():
    raise NotImplementedError
