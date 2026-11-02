# boq — automated quantity take-off & BoQ generator

Ingests a project's drawing set, extracts measurable quantities, and produces a priced Bill of
Quantities, an internal analysis, and a structured record for the CRM.

**This is a decision-support and estimating aid, not a certified take-off.** Every number is
traceable to a source region and must be reviewed by an engineer before it reaches a client.

---

## Status

| Phase | State |
|---|---|
| Template analysis | ✅ [`docs/template-analysis.md`](docs/template-analysis.md) |
| **Phase 0** — repo scaffold | ✅ this commit |
| **Phase 1** — ingest + classify | ⬜ not started |
| **Phase 2** — table extractors | 🟡 partial — see below |
| **Phase 3** — derived quantities + schema | ✅ engine, schema v1.1.0, wastage at reporting time |
| **Phase 4** — thermal set + cross-checks | ✅ delivered within Phases 2–3 |
| **Phase 5** — rate library + BoQ writer | 🟡 xlsx done; PDF pending (needs letterhead + Arabic font) |
| **Phase 6** — engineer review screen | ✅ local web UI, audit trail, export gate |
| Phases 7–8 | ⬜ not started |

### Phase 2 detail

| Extractor | State |
|---|---|
| Area schedule (Set A, N04) | ✅ validated against the real sheet |
| Thermal workbook (Set C) | ✅ validated against real captured cell data |
| Cross-check engine | ✅ 7 checks, validated on the real sample |
| Footing schedule (Set B, ST-02) | ✅ validated against the real sheet |
| Column schedule (Set B, ST-02) | ✅ validated against the real sheet |
| Door & window schedules (Set A, A09/A10) | ⛔ blocked — needs `DCR2564_FINAL_DRAWINGS.pdf` |
| Bar bending schedule | ⚪ not applicable — Set B contains no BBS |

Phase 3 runs on whatever Phase 2 produces. On the sample it derives 32 quantities and
emits 16 explicit nulls, each with a reason and one of three codes that separate a limit of
the documents from a limit of this tool:

| Code | Meaning | On DCR2564 |
|---|---|---|
| `not-issued` | designed, but delegated | 5 — PT slabs, tendons, anchorages |
| `needs-plan-geometry` | section scheduled, length only on the plan | 3 — strip footings, beams, ground slab |
| `extractor-not-built` | readable schedule, parser blocked | 4 — columns, ground beams, steel, formwork |

The one remaining blocked extractor is a positional parser. The analysis session captured their
*text* but not their per-word coordinates. Writing a positional parser against a guessed
layout, then testing it on a fixture that invented those positions, would be circular — it
would prove nothing about the real sheet. `STR2564.pdf` has since been recovered from Drive
and its two schedules are done; `DCR2564_FINAL_DRAWINGS.pdf` is 9 MB, which exceeds what the
Drive connector can return in one response, so the door and window schedules still wait on
a direct upload.

Per the build prompt, work stops at the end of each phase for review.

---

## The one thing to understand first

These drawings are AutoCAD plots. **The PDF text layer is emitted in draw order, not layout
order**, so reading order is useless. The area schedule reads like this in document order:

```
170.8 SQ.M.  %  SQ.M.  TOTAL  406.9 SQ.M.  SQ.M.  89.8  %  132.5  SQ.M.  35.4  132.5  336.2
```

Everything therefore starts from `boq.text`: extract words with coordinates, cluster them by
baseline, sort left to right. See [`docs/template-analysis.md`](docs/template-analysis.md)
section 4.

```python
from boq.text.words import words_from_pdf
from boq.extract.architectural import area_schedule

words = words_from_pdf("DCR2564_FINAL_DRAWINGS.pdf", page_index=4)
schedule = area_schedule.parse(words)

print(schedule.total_built_up)  # 406.9
print(schedule.check())  # [] -- all internal identities hold
```

---

## Layout

```
src/boq/
  text/        positional reconstruction — words, rows, viewport separation
  ingest/      upload, hashing, project folders
  classify/    page → discipline, sheet type, title-block fields
  extract/     per-discipline extractors (structural, architectural, thermal, mep)
  normalize/   raw findings → canonical schema
  rules/       derived quantities: volumes, formwork, steel mass, block counts
  crosscheck/  consistency tests, runnable headless in CI
  rates/       rate library loader, versioned
  report/      BoQ writer (xlsx, pdf), analysis
  review/      engineer review UI + audit trail
  crm/         adapter interface + LocalFileAdapter
schema/        project_quantities.v1.json — the extraction↔reporting contract
config/        factors.yaml (wastage, unit masses, conventions)
rates/         rates.yaml — empty until the office supplies real rates
tools/         make_fixtures.py
```

## The review screen

The mandatory gate between extraction and BoQ issue (build prompt section 7):

```bash
python tools/review.py --drawings /path/to/project/pdfs --reviewer "S.Abbas"
# Review screen on http://127.0.0.1:8765
```

Extracted table on the left, the cited source page with its region highlighted on the right,
items ordered lowest confidence first. Approve, correct or reject inline; every action is
recorded in an append-only audit trail with who, when and from what to what. A correction
becomes an `assumed` quantity and lands on the Assumptions sheet — an engineer-supplied number
is an assumption, whatever produced the original.

Nothing exports while a low-confidence item is unresolved or a blocking cross-check stands. A
failing check can be accepted with a named reason; it keeps its failing status, but someone
owns the decision.

Built on the standard library's `http.server` — no web framework, so it runs on any machine
with Python. Binds to localhost: it serves unreviewed client quantities and has no auth.

## Setup

```bash
uv venv && uv pip install -e ".[dev]"
pre-commit install
pytest
```

Note: if `pip3` and `python3` disagree on version, use `python3 -m pip`.

---

## Non-negotiables

These come from section 11 of the build prompt and are enforced in code and schema:

1. **Never fabricate a quantity, dimension, rate or code clause.** Missing → `null` plus a
   reason. The schema *requires* `null_reason` whenever `quantity` is null.
2. **No number without a source.** If it cannot be traced to a page region or spreadsheet cell,
   it is not emitted. A `pdf` source requires `page` and `bbox`.
3. **Never change an extractor's behaviour just to make a test pass** — fix it or fail loudly.
4. **Deterministic logic goes in plain code, not a model call.** Models read documents; they
   never compute totals.
5. **Wastage and lap allowances are applied at reporting time only**, never baked into an
   extracted quantity.
6. Every model call is logged with its prompt, page reference and cost.
7. Rates are never invented. No rate → the item is flagged `rate required`.

## Test data

Real client drawings are **not** committed. `tests/fixtures/` holds anonymised extracted word
lists only, regenerated with `tools/make_fixtures.py`, which strips names, phone numbers,
email addresses and permit references.

## Blocked on the office

- The **manually prepared BoQ for DCR2564** — needed for the Phase-13 validation baseline.
- **Blocks per m²** for 200 mm thermal block and 100/150/200 mm solid block
  (`config/factors.yaml` leaves these `null` deliberately).
- The **rate library** (`rates/rates.yaml` is empty by design).
- The **CRM** target: name, API base URL, auth method, module.

Full list: [`docs/template-analysis.md`](docs/template-analysis.md) section 12.
