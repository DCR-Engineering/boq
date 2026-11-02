"""The engineer review screen.

A local web UI over :class:`~boq.review.session.ReviewSession`, built on the standard
library's ``http.server``. No web framework: this runs on any machine with Python, which
matters more for an office tool than framework conveniences do.

Layout follows build prompt section 7 -- extracted table on the left, the cited source page
with its region highlighted on the right, lowest confidence first, with a cross-check panel
and an export gate.

Bind to localhost. This serves unreviewed client quantities and has no authentication.
"""

from __future__ import annotations

import html
import json
import urllib.parse
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

from boq.review.render import RenderError, can_render, render_source
from boq.review.session import ReviewSession, ReviewStatus

_STYLE = """
:root {
  --bg: #fbfbfa; --panel: #ffffff; --ink: #1d1d1b; --muted: #6b6b66;
  --line: #e3e3df; --accent: #1f4e78; --warn: #b45309; --bad: #b3261e;
  --ok: #176b3a; --chip: #f1f1ee;
}
@media (prefers-color-scheme: dark) {
  :root:not([data-theme="light"]) {
    --bg: #15151a; --panel: #1d1d23; --ink: #ececf0; --muted: #9b9ba6;
    --line: #2f2f38; --accent: #7ba7d4; --warn: #e0a955; --bad: #f2695e;
    --ok: #4ec07e; --chip: #26262e;
  }
}
* { box-sizing: border-box; }
body { margin:0; background:var(--bg); color:var(--ink);
  font:15px/1.5 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif; }
a { color:var(--accent); }
header { padding:14px 20px; border-bottom:1px solid var(--line); background:var(--panel);
  display:flex; gap:16px; align-items:baseline; flex-wrap:wrap; position:sticky; top:0; z-index:5;}
header h1 { font-size:16px; margin:0; font-weight:650; }
header .sp { flex:1; }
.wrap { padding:20px; max-width:1500px; margin:0 auto; }
.grid { display:grid; grid-template-columns: 1fr 1fr; gap:20px; align-items:start; }
@media (max-width: 1000px) { .grid { grid-template-columns: 1fr; } }
.card { background:var(--panel); border:1px solid var(--line); border-radius:10px;
  padding:16px; margin-bottom:18px; }
h2 { font-size:14px; text-transform:uppercase; letter-spacing:.06em; color:var(--muted);
  margin:0 0 12px; }
table { width:100%; border-collapse:collapse; font-size:14px; }
th, td { text-align:left; padding:7px 8px; border-bottom:1px solid var(--line);
  vertical-align:top; }
th { color:var(--muted); font-weight:600; font-size:12px; text-transform:uppercase;
  letter-spacing:.04em; }
tr:last-child td { border-bottom:none; }
.num { text-align:right; font-variant-numeric:tabular-nums; white-space:nowrap; }
.chip { display:inline-block; padding:1px 8px; border-radius:999px; background:var(--chip);
  font-size:12px; color:var(--muted); }
.bad { color:var(--bad); } .ok { color:var(--ok); } .warn { color:var(--warn); }
.banner { padding:12px 16px; border-radius:10px; margin-bottom:18px; font-weight:600; }
.banner.block { background:#fdecea; color:#8c1d18; border:1px solid #f3c6c2; }
.banner.go { background:#e7f5ec; color:#14532d; border:1px solid #bfe3cd; }
@media (prefers-color-scheme: dark) { :root:not([data-theme="light"]) .banner.block {
  background:#3a1a18; color:#ffb4ab; border-color:#5c2a26; }
  :root:not([data-theme="light"]) .banner.go { background:#17301f; color:#90d6a8;
  border-color:#2a4d35; } }
.pagewrap { position:relative; display:inline-block; max-width:100%; }
.pagewrap img { width:100%; height:auto; border:1px solid var(--line); border-radius:6px;
  display:block; }
.hl { position:absolute; border:2px solid var(--bad); background:rgba(179,38,30,.12);
  border-radius:3px; pointer-events:none; }
form.inline { display:flex; gap:8px; align-items:center; flex-wrap:wrap; margin-top:10px; }
input[type=text], input[type=number] { padding:7px 9px; border:1px solid var(--line);
  border-radius:7px; background:var(--bg); color:var(--ink); font:inherit; }
input[type=text] { min-width:220px; }
button { padding:7px 14px; border-radius:7px; border:1px solid var(--line);
  background:var(--accent); color:#fff; font:inherit; font-weight:600; cursor:pointer; }
button.sec { background:transparent; color:var(--ink); }
button.danger { background:var(--bad); }
.small { font-size:12px; color:var(--muted); }
code { background:var(--chip); padding:1px 5px; border-radius:4px; font-size:12.5px; }
.missing { padding:28px; text-align:center; color:var(--muted); border:1px dashed var(--line);
  border-radius:8px; }
"""


def _e(value: Any) -> str:
    return html.escape("" if value is None else str(value))


def _blocking_cell(check) -> str:
    hot = check.blocking and check.status in ("fail", "not_possible")
    return "<b class=bad>blocking</b>" if hot else ""


def _qty(item) -> str:
    if item.quantity is None:
        return "—"
    return f"{item.quantity:,.3f}"


@dataclass
class ReviewApp:
    """Serves one review session."""

    session: ReviewSession
    search_dirs: list[Path]
    reviewer: str = "engineer"

    # -- pages ------------------------------------------------------------------

    def index(self) -> str:
        s = self.session
        queue = s.queue
        blockers = s.export_blockers()

        banner = (
            '<div class="banner go">Ready to export — '
            "every low-confidence item resolved and no blocking cross-check outstanding.</div>"
            if s.can_export
            else f'<div class="banner block">Export blocked — {len(blockers)} '
            f"item{'s' if len(blockers) != 1 else ''} outstanding.</div>"
        )

        rows = "".join(
            f"<tr><td><a href='/item/{_e(i.id)}'>{_e(i.id)}</a><div class='small'>"
            f"{_e(i.element)}</div></td>"
            f"<td class='num'>{_qty(i)}</td><td>{_e(i.unit)}</td>"
            f"<td class='num {'bad' if i.confidence < s.threshold else ''}'>"
            f"{i.confidence:.0%}</td>"
            f"<td><span class='chip'>{_e(i.method)}</span></td>"
            f"<td>{self._status_cell(i.id)}</td></tr>"
            for i in s.items
        )

        queue_rows = (
            "".join(
                f"<tr><td><a href='/item/{_e(i.id)}'>{_e(i.id)}</a></td>"
                f"<td class='num bad'>{i.confidence:.0%}</td>"
                f"<td class='small'>{_e(i.element)}</td></tr>"
                for i in queue
            )
            or "<tr><td colspan='3' class='small ok'>Nothing outstanding.</td></tr>"
        )

        checks = "".join(
            f"<tr><td>{_e(c.check_id)}</td>"
            f"<td class='{self._check_class(c)}'>{_e(c.status)}</td>"
            f"<td>{_blocking_cell(c)}</td>"
            f"<td class='small'>{_e(c.detail)}"
            + (
                f"<form class='inline' method='post' action='/check/{_e(c.check_id)}/accept'>"
                f"<input type='text' name='comment' placeholder='reason for accepting' required>"
                f"<input type='hidden' name='by' value='{_e(self.reviewer)}'>"
                f"<button class='sec'>Accept</button></form>"
                if c.blocking and c.status in ("fail", "not_possible")
                else ""
            )
            + "</td></tr>"
            for c in s.cross_checks
        )

        summary = s.summary()
        return self._page(
            "Review",
            f"""
{banner}
<div class="grid">
  <div>
    <div class="card"><h2>Outstanding — lowest confidence first</h2>
      <table><tr><th>Item</th><th class='num'>Conf.</th><th>Description</th></tr>
      {queue_rows}</table></div>
    <div class="card"><h2>Summary</h2>
      <table>
      <tr><th>Items</th><td class='num'>{summary["total_items"]}</td></tr>
      <tr><th>Reviewed</th><td class='num'>{s.reviewed_count}</td></tr>
      <tr><th>Outstanding low-confidence</th>
          <td class='num'>{summary["outstanding_low_confidence"]}</td></tr>
      <tr><th>Threshold</th><td class='num'>{s.threshold:.0%}</td></tr>
      <tr><th>Can export</th><td class='num {"ok" if s.can_export else "bad"}'>
        {"yes" if s.can_export else "no"}</td></tr>
      </table></div>
  </div>
  <div class="card"><h2>Cross-checks</h2>
    <table><tr><th>Check</th><th>Status</th><th></th><th>Detail</th></tr>{checks}</table></div>
</div>
<div class="card"><h2>All quantities</h2>
  <table><tr><th>Item</th><th class='num'>Qty</th><th>Unit</th><th class='num'>Conf.</th>
  <th>Method</th><th>Review</th></tr>{rows}</table></div>
""",
        )

    def item_page(self, item_id: str) -> str:
        s = self.session
        item = s.item(item_id)
        state = s.state(item_id)
        src = item.source

        if can_render(src, self.search_dirs):
            pane = (
                f"<div class='pagewrap'><img src='/page/{urllib.parse.quote(item_id)}.png' "
                f"alt='source page'><div id='hl'></div></div>"
                f"<p class='small'>{_e(src.file)} — page {_e(src.page)}"
                + (f", {_e(src.region)}" if src.region else "")
                + "</p>"
                f"<script>fetch('/hl/{urllib.parse.quote(item_id)}.json')"
                ".then(r=>r.json()).then(h=>{if(!h)return;const i=document.querySelector"
                "('.pagewrap img');const d=document.getElementById('hl');"
                "const draw=()=>{const k=i.clientWidth/i.naturalWidth;d.className='hl';"
                "d.style.left=h.left*k+'px';d.style.top=h.top*k+'px';"
                "d.style.width=h.width*k+'px';d.style.height=h.height*k+'px';};"
                "i.complete?draw():i.onload=draw;addEventListener('resize',draw);});</script>"
            )
        else:
            pane = (
                "<div class='missing'>Source page not available.<br>"
                f"<span class='small'>{_e(src.file)}"
                + (f" — page {_e(src.page)}" if src.page else "")
                + (f", cell {_e(src.cell)}" if src.cell else "")
                + "<br>Drawing files are not kept in the repository. Start the server with "
                "<code>--drawings &lt;folder&gt;</code> to show them.</span></div>"
            )

        spec = (
            "".join(f"<tr><th>{_e(k)}</th><td>{_e(v)}</td></tr>" for k, v in item.spec.items())
            if item.spec
            else ""
        )
        audit = (
            "".join(
                f"<tr><td class='small'>{_e(a.at)}</td><td>{_e(a.by)}</td>"
                f"<td><span class='chip'>{_e(a.action)}</span></td>"
                f"<td class='num'>{_e(a.from_value)}</td><td class='num'>{_e(a.to_value)}</td>"
                f"<td class='small'>{_e(a.comment)}</td></tr>"
                for a in s.audit
                if a.item_id == item_id
            )
            or "<tr><td colspan='6' class='small'>No actions recorded.</td></tr>"
        )

        formula_row = (
            f"<tr><th>Formula</th><td><code>{_e(item.formula)}</code></td></tr>"
            if item.formula
            else ""
        )
        null_row = (
            f"<tr><th>Not available</th><td class='bad'>{_e(item.null_reason)}</td></tr>"
            if item.null_reason
            else ""
        )
        flags_row = (
            "<tr><th>Flags</th><td>"
            + "".join(f"<span class=chip>{_e(f)}</span> " for f in item.flags)
            + "</td></tr>"
            if item.flags
            else ""
        )
        notes_row = (
            f"<tr><th>Notes</th><td class='small'>{_e(item.notes)}</td></tr>" if item.notes else ""
        )
        state_rows = (
            f"<div class='small'>by {_e(state.by)} at {_e(state.at)}</div>" if state.by else ""
        ) + (
            f"<div class='small'>was {_e(state.original_value)}</div>"
            if state.original_value is not None
            else ""
        )

        return self._page(
            item_id,
            f"""
<p><a href="/">← back to review</a></p>
<div class="grid">
  <div>
    <div class="card"><h2>{_e(item.id)}</h2>
      <table>
        <tr><th>Description</th><td>{_e(item.element)}</td></tr>
        <tr><th>Quantity</th><td class='num'><b>{_qty(item)}</b> {_e(item.unit)}</td></tr>
        <tr><th>Method</th><td><span class='chip'>{_e(item.method)}</span></td></tr>
        <tr><th>Confidence</th>
            <td class='num {"bad" if item.confidence < s.threshold else "ok"}'>
            {item.confidence:.0%}</td></tr>
        <tr><th>Trade / level</th><td>{_e(item.trade)} {_e(item.level or "")}</td></tr>
        {formula_row}
        {null_row}
        {flags_row}
        {notes_row}
        <tr><th>Source</th><td class='small'>{_e(src.file)}
            {f"page {_e(src.page)}" if src.page else ""}
            {f"sheet {_e(src.sheet)}" if src.sheet else ""}
            {f"cell {_e(src.cell)}" if src.cell else ""}</td></tr>
        {spec}
        <tr><th>Review</th><td>{self._status_cell(item_id)}{state_rows}</td></tr>
      </table>

      <form class="inline" method="post" action="/item/{_e(item_id)}/approve">
        <input type="hidden" name="by" value="{_e(self.reviewer)}">
        <input type="text" name="comment" placeholder="comment (optional)">
        <button>Approve as extracted</button>
      </form>
      <form class="inline" method="post" action="/item/{_e(item_id)}/correct">
        <input type="hidden" name="by" value="{_e(self.reviewer)}">
        <input type="number" step="any" min="0" name="value" placeholder="corrected value" required>
        <input type="text" name="comment" placeholder="why">
        <button class="sec">Correct</button>
      </form>
      <form class="inline" method="post" action="/item/{_e(item_id)}/reject">
        <input type="hidden" name="by" value="{_e(self.reviewer)}">
        <input type="text" name="comment" placeholder="reason (required)" required>
        <button class="danger">Reject</button>
      </form>
      <p class="small">A correction is recorded as an assumption by {_e(self.reviewer)} and
      appears on the Assumptions sheet of the BoQ. The extracted value is kept in the audit
      trail.</p>
    </div>
    <div class="card"><h2>Audit trail for this item</h2>
      <table><tr><th>When</th><th>Who</th><th>Action</th><th class='num'>From</th>
      <th class='num'>To</th><th>Comment</th></tr>{audit}</table></div>
  </div>
  <div class="card"><h2>Source</h2>{pane}</div>
</div>
""",
        )

    def audit_page(self) -> str:
        rows = (
            "".join(
                f"<tr><td class='small'>{_e(a.at)}</td><td>{_e(a.by)}</td>"
                f"<td><a href='/item/{_e(a.item_id)}'>{_e(a.item_id)}</a></td>"
                f"<td><span class='chip'>{_e(a.action)}</span></td>"
                f"<td class='num'>{_e(a.from_value)}</td><td class='num'>{_e(a.to_value)}</td>"
                f"<td class='small'>{_e(a.comment)}</td></tr>"
                for a in self.session.audit
            )
            or "<tr><td colspan='7' class='small'>No actions recorded yet.</td></tr>"
        )
        return self._page(
            "Audit trail",
            f"""<p><a href="/">← back to review</a></p>
<div class="card"><h2>Audit trail</h2>
<table><tr><th>When</th><th>Who</th><th>Item</th><th>Action</th><th class='num'>From</th>
<th class='num'>To</th><th>Comment</th></tr>{rows}</table></div>""",
        )

    # -- helpers ----------------------------------------------------------------------

    def _status_cell(self, item_id: str) -> str:
        state = self.session.state(item_id)
        cls = {
            ReviewStatus.APPROVED: "ok",
            ReviewStatus.CORRECTED: "warn",
            ReviewStatus.REJECTED: "bad",
            ReviewStatus.UNREVIEWED: "small",
        }[state.status]
        return f"<span class='{cls}'>{_e(state.status.value)}</span>"

    @staticmethod
    def _check_class(check) -> str:
        return {"pass": "ok", "reconciled": "ok", "fail": "bad"}.get(check.status, "small")

    def _page(self, title: str, body: str) -> str:
        project = self.session.project
        return f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{_e(title)} — BoQ review</title><style>{_STYLE}</style></head><body>
<header><h1>BoQ review</h1>
<span class="chip">{_e(project.get("project_no", ""))}</span>
<span class="small">{_e(project.get("title", ""))}</span>
<span class="sp"></span>
<span class="small">reviewer: <b>{_e(self.reviewer)}</b></span>
<a href="/">Queue</a><a href="/audit">Audit</a></header>
<div class="wrap">{body}</div></body></html>"""


class _Handler(BaseHTTPRequestHandler):
    app: ReviewApp

    def log_message(self, *_args: Any) -> None:  # quiet by default
        pass

    # -- GET ------------------------------------------------------------------------

    def do_GET(self) -> None:  # http.server API naming
        path = urllib.parse.urlparse(self.path).path
        try:
            if path == "/":
                return self._html(self.app.index())
            if path == "/audit":
                return self._html(self.app.audit_page())
            if path.startswith("/item/"):
                return self._html(self.app.item_page(urllib.parse.unquote(path[6:])))
            if path.startswith("/page/") and path.endswith(".png"):
                return self._png(urllib.parse.unquote(path[6:-4]))
            if path.startswith("/hl/") and path.endswith(".json"):
                return self._highlight(urllib.parse.unquote(path[4:-5]))
            if path == "/document.json":
                return self._json(self.app.session.to_document())
            self._error(404, "Not found")
        except Exception as exc:  # surface the reason rather than a blank 500
            self._error(400, str(exc))

    def _png(self, item_id: str) -> None:
        item = self.app.session.item(item_id)
        try:
            region = render_source(item.source, search_dirs=self.app.search_dirs)
        except RenderError as exc:
            return self._error(404, str(exc))
        self.send_response(200)
        self.send_header("Content-Type", "image/png")
        self.send_header("Content-Length", str(len(region.png)))
        self.end_headers()
        self.wfile.write(region.png)

    def _highlight(self, item_id: str) -> None:
        item = self.app.session.item(item_id)
        try:
            region = render_source(item.source, search_dirs=self.app.search_dirs, draw_box=False)
        except RenderError:
            return self._json(None)
        self._json(region.highlight_css)

    # -- POST -----------------------------------------------------------------------

    def do_POST(self) -> None:  # http.server API naming
        path = urllib.parse.urlparse(self.path).path
        length = int(self.headers.get("Content-Length") or 0)
        form = urllib.parse.parse_qs(self.rfile.read(length).decode("utf-8"))
        get = lambda k, d="": (form.get(k) or [d])[0]  # noqa: E731

        session = self.app.session
        try:
            if path.startswith("/item/") and path.endswith("/approve"):
                session.approve(path[6:-8], get("by", self.app.reviewer), get("comment"))
                return self._redirect(f"/item/{path[6:-8]}")
            if path.startswith("/item/") and path.endswith("/correct"):
                session.correct(
                    path[6:-8],
                    float(get("value")),
                    get("by", self.app.reviewer),
                    get("comment"),
                )
                return self._redirect(f"/item/{path[6:-8]}")
            if path.startswith("/item/") and path.endswith("/reject"):
                session.reject(path[6:-7], get("by", self.app.reviewer), get("comment"))
                return self._redirect(f"/item/{path[6:-7]}")
            if path.startswith("/check/") and path.endswith("/accept"):
                session.resolve_check(path[7:-7], get("by", self.app.reviewer), get("comment"))
                return self._redirect("/")
            self._error(404, "Not found")
        except Exception as exc:
            self._error(400, str(exc))

    # -- responses --------------------------------------------------------------------

    def _html(self, body: str) -> None:
        data = body.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _json(self, payload: Any) -> None:
        data = json.dumps(payload).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _redirect(self, location: str) -> None:
        self.send_response(303)
        self.send_header("Location", location)
        self.end_headers()

    def _error(self, code: int, message: str) -> None:
        data = f"<pre>{html.escape(message)}</pre>".encode()
        self.send_response(code)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)


def make_server(
    session: ReviewSession,
    *,
    drawings: list[Path] | None = None,
    reviewer: str = "engineer",
    host: str = "127.0.0.1",
    port: int = 8765,
) -> ThreadingHTTPServer:
    """Build (but do not start) the review server.

    Binds to localhost by default: this serves unreviewed client quantities and has no
    authentication.
    """
    app = ReviewApp(session=session, search_dirs=list(drawings or []), reviewer=reviewer)
    handler = type("BoundHandler", (_Handler,), {"app": app})
    return ThreadingHTTPServer((host, port), handler)


def serve(session: ReviewSession, **kwargs: Any) -> None:
    """Run the review server until interrupted."""
    server = make_server(session, **kwargs)
    host, port = server.server_address[:2]
    print(f"Review screen on http://{host}:{port}  (Ctrl-C to stop)")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
