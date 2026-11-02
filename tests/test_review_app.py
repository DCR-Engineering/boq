"""Review web UI tests.

Drives a real server over HTTP rather than calling handler methods, so routing, form posting
and redirects are covered as an engineer would exercise them.
"""

from __future__ import annotations

import json
import threading
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

import pytest

from boq.extract.architectural import area_schedule
from boq.extract.thermal import thermal_calc
from boq.extract.thermal.workbook import CellMap
from boq.normalize.items import Source
from boq.review.app import make_server
from boq.review.render import RenderError, can_render, render_source
from boq.review.session import ReviewSession, ReviewStatus
from boq.rules import engine
from boq.text.words import load_words

FIXTURES = Path(__file__).parent / "fixtures" / "DCR2564"
# The real drawings are not in the repository; this is where the session downloaded them.
SAMPLES = Path(
    "/tmp/claude-0/-home-user-boq/0196a0ef-711f-5764-b277-cc366f5700e1/scratchpad/samples"
)

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


def _session() -> ReviewSession:
    payload = json.loads((FIXTURES / "thermal_workbook.cells.json").read_text(encoding="utf-8"))
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
    return ReviewSession(result)


@pytest.fixture
def server():
    session = _session()
    srv = make_server(session, drawings=[SAMPLES], reviewer="S.Abbas", port=0)
    thread = threading.Thread(target=srv.serve_forever, daemon=True)
    thread.start()
    host, port = srv.server_address[:2]
    try:
        yield f"http://{host}:{port}", session
    finally:
        srv.shutdown()
        srv.server_close()
        thread.join(timeout=5)


def _get(base: str, path: str):
    try:
        with urllib.request.urlopen(base + path, timeout=10) as r:  # localhost only
            return r.status, r.read()
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read()


def _post(base: str, path: str, **fields):
    data = urllib.parse.urlencode(fields).encode()
    req = urllib.request.Request(base + path, data=data, method="POST")
    opener = urllib.request.build_opener(_NoRedirect)
    try:
        with opener.open(req, timeout=10) as r:  # localhost only
            return r.status, r.read()
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read()


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *_args, **_kwargs):
        return None


# -- pages ------------------------------------------------------------------------


def test_index_renders(server):
    base, _ = server
    status, body = _get(base, "/")
    assert status == 200
    text = body.decode()
    assert "BoQ review" in text
    assert "DCR2564" in text


def test_index_shows_export_blocked(server):
    base, _ = server
    _, body = _get(base, "/")
    assert "Export blocked" in body.decode()


def test_index_lists_the_queue_lowest_confidence_first(server):
    base, session = server
    _, body = _get(base, "/")
    text = body.decode()
    ids = [i.id for i in session.queue]
    positions = [text.index(i) for i in ids]
    assert positions == sorted(positions)


def test_index_shows_cross_checks(server):
    base, _ = server
    _, body = _get(base, "/")
    text = body.decode()
    assert "envelope_decomposition" in text
    assert "thermal_spreadsheet_errors" in text


def test_item_page_renders(server):
    base, _ = server
    status, body = _get(base, "/item/block.external.area")
    assert status == 200
    text = body.decode()
    assert "block.external.area" in text
    assert "529.606" in text


def test_item_page_shows_the_null_reason(server):
    base, _ = server
    _, body = _get(base, "/item/conc.slab.pt.first")
    assert "PT SPECIALIST" in body.decode()


def test_unknown_item_is_an_error_not_a_crash(server):
    base, _ = server
    status, _ = _get(base, "/item/no.such.item")
    assert status == 400


def test_audit_page_renders(server):
    base, _ = server
    status, body = _get(base, "/audit")
    assert status == 200
    assert "Audit trail" in body.decode()


# -- actions over HTTP --------------------------------------------------------------


def test_approve_via_post(server):
    base, session = server
    status, _ = _post(base, "/item/finish.paint.external/approve", by="S.Abbas", comment="ok")
    assert status == 303
    assert session.state("finish.paint.external").status is ReviewStatus.APPROVED


def test_correct_via_post(server):
    base, session = server
    status, _ = _post(
        base,
        "/item/finish.plaster.external/correct",
        by="S.Abbas",
        value="900",
        comment="measured",
    )
    assert status == 303
    assert session.item("finish.plaster.external").quantity == 900.0
    assert session.state("finish.plaster.external").original_value == pytest.approx(1059.212)


def test_reject_via_post(server):
    base, session = server
    status, _ = _post(
        base, "/item/finish.paint.external/reject", by="S.Abbas", comment="no schedule"
    )
    assert status == 303
    assert session.item("finish.paint.external").quantity is None


def test_reject_without_a_reason_is_refused(server):
    base, session = server
    status, _ = _post(base, "/item/finish.paint.external/reject", by="S.Abbas", comment="")
    assert status == 400
    assert session.item("finish.paint.external").quantity is not None


def test_accept_a_cross_check_via_post(server):
    base, session = server
    check = session.outstanding_checks()[0]
    status, _ = _post(
        base, f"/check/{check.check_id}/accept", by="S.Abbas", comment="client confirmed"
    )
    assert status == 303
    assert not check.blocking


def test_actions_appear_in_the_audit_page(server):
    base, _ = server
    _post(base, "/item/finish.paint.external/approve", by="S.Abbas", comment="verified")
    _, body = _get(base, "/audit")
    text = body.decode()
    assert "S.Abbas" in text
    assert "verified" in text


def test_document_endpoint_is_schema_valid(server):
    from boq.normalize.items import validate

    base, _ = server
    _post(base, "/item/finish.paint.external/approve", by="S.Abbas")
    status, body = _get(base, "/document.json")
    assert status == 200
    doc = json.loads(body)
    assert validate(doc) == []


def test_html_is_escaped(server):
    """A reviewer comment must not be able to inject markup."""
    base, _ = server
    _post(
        base,
        "/item/finish.paint.external/approve",
        by="S.Abbas",
        comment="<script>alert(1)</script>",
    )
    _, body = _get(base, "/audit")
    text = body.decode()
    assert "<script>alert(1)</script>" not in text
    assert "&lt;script&gt;" in text


# -- source rendering ----------------------------------------------------------------


@pytest.mark.integration
def test_renders_the_real_structural_page_with_a_highlight():
    """The right-hand pane, against the actual STR2564.pdf."""
    pdf = SAMPLES / "STR2564.pdf"
    if not pdf.exists():
        pytest.skip("STR2564.pdf not present in this environment")

    source = Source(
        file="STR2564.pdf",
        file_type="pdf",
        page=5,
        sheet="ST - 02",
        region="footing schedule",
        bbox=(1255.0, 865.0, 1520.0, 950.0),
    )
    region = render_source(source, search_dirs=[SAMPLES])
    assert region.png.startswith(b"\x89PNG")
    assert region.page_width > region.page_height, "ST-02 is landscape once rotation applies"
    css = region.highlight_css
    assert css["left"] > 0 and css["width"] > 0


def test_missing_drawing_file_is_reported_not_crashed():
    source = Source(file="NOT_HERE.pdf", file_type="pdf", page=1, bbox=(0.0, 0.0, 10.0, 10.0))
    assert not can_render(source, [SAMPLES])
    with pytest.raises(RenderError, match="not found"):
        render_source(source, search_dirs=[SAMPLES])


def test_spreadsheet_sources_cannot_be_rendered():
    source = Source(file="x.xlsx", file_type="xlsx", sheet="Main", cell="A18")
    assert not can_render(source, [SAMPLES])
    with pytest.raises(RenderError, match="only PDF"):
        render_source(source, search_dirs=[SAMPLES])


def test_item_page_explains_a_missing_source(server):
    """Thermal items cite a spreadsheet cell, which has no page to show."""
    base, _ = server
    _, body = _get(base, "/item/glaz.window.W17")
    text = body.decode()
    assert "Source page not available" in text
    assert "Main" in text


@pytest.mark.integration
def test_highlight_is_actually_drawn_on_a_rotated_page():
    """Regression: annotations take unrotated coordinates.

    ST-02 is plotted with /Rotate 270 and a stored bbox is in rendered space. Without
    derotating, add_rect_annot places the box off-page and nothing raises -- the review
    screen just shows an unhighlighted sheet. Checking for red pixels on the expected
    border is the only way to catch that.
    """
    import pymupdf

    pdf = SAMPLES / "STR2564.pdf"
    if not pdf.exists():
        pytest.skip("STR2564.pdf not present in this environment")

    source = Source(
        file="STR2564.pdf",
        file_type="pdf",
        page=5,
        sheet="ST - 02",
        region="footing schedule",
        bbox=(1255.0, 865.0, 1520.0, 950.0),
    )
    region = render_source(source, search_dirs=[SAMPLES])
    pix = pymupdf.Pixmap(region.png)
    css = region.highlight_css

    x0, y0 = int(css["left"]), int(css["top"])
    x1, y1 = int(x0 + css["width"]), int(y0 + css["height"])

    def is_red(x: int, y: int) -> bool:
        r, g, b = pix.pixel(x, y)[:3]
        return r > 150 and g < 110 and b < 110

    edges = {
        "top": sum(is_red(x, y0) for x in range(x0, x1, 2)),
        "bottom": sum(is_red(x, y1) for x in range(x0, x1, 2)),
        "left": sum(is_red(x0, y) for y in range(y0, y1, 2)),
        "right": sum(is_red(x1, y) for y in range(y0, y1, 2)),
    }
    assert all(count > 5 for count in edges.values()), f"highlight not drawn: {edges}"
