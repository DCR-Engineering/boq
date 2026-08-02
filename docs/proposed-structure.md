# Proposed repo structure, v1 schema and assumptions

Companion to [`template-analysis.md`](./template-analysis.md). Nothing here is built yet —
this is the proposal to approve before Phase 0 starts.

---

## 1. Repo layout

```
boq/
├── pyproject.toml              # Python 3.11+, uv, ruff, pytest
├── .pre-commit-config.yaml
├── .env.example                # no secrets in repo
├── README.md
├── .github/workflows/ci.yml    # ruff + pytest + schema validation
│
├── src/boq/
│   ├── ingest/                 # upload, SHA-256 hashing, project folder layout
│   │   ├── project.py          #   Project / DocumentSet / SourceFile
│   │   └── inventory.py        #   per-file: pages, fonts, text-layer presence
│   │
│   ├── classify/               # page -> discipline, sheet type, sheet no, title block
│   │   ├── titleblock.py       #   label-anchored field reader (docs §2)
│   │   ├── sheet_index.py      #   Set A index table; DWF manifest reader
│   │   └── page_class.py
│   │
│   ├── text/                   # ** the core primitive — build first **
│   │   ├── words.py            #   positional word extraction
│   │   ├── rows.py             #   y-bucket / x-sort reconstruction (docs §4)
│   │   ├── viewport.py         #   gap-based plan/legend separation (docs §6.6)
│   │   └── grid.py             #   column detection from x-histograms
│   │
│   ├── extract/
│   │   ├── structural/         #   footing, column, ground beam, beam, slab schedules
│   │   ├── architectural/      #   area table, door cards, window cards, room annotation
│   │   ├── thermal/            #   xlsx reader: Main, wall, glass, U-values
│   │   ├── mep/                #   symbol counts, pipe runs        (Phase 7)
│   │   └── vision/             #   rasterize + model pass, logged  (Phase 3+)
│   │
│   ├── normalize/              # raw findings -> canonical schema, units, marks
│   ├── rules/                  # deterministic derivation: volumes, formwork, steel, blocks
│   ├── crosscheck/             # the consistency tests in docs §8
│   ├── rates/                  # rates.yaml loader, versioning, low/expected/high
│   ├── report/                 # xlsx writer (formulas live), pdf, analysis
│   ├── review/                 # engineer review UI + audit trail
│   └── crm/
│       ├── adapter.py          #   thin interface
│       └── local_file.py       #   LocalFileAdapter for dev
│
├── schema/
│   └── project_quantities.v1.json
│
├── config/
│   ├── factors.yaml            # blocks/m², wastage, lap allowances — all editable
│   └── codes/bahrain.yaml      # thermal limits, BS 8110 params
│
├── rates/
│   └── rates.yaml
│
├── docs/
│   ├── template-analysis.md
│   └── proposed-structure.md
│
└── tests/
    ├── fixtures/DCR2564/       # anonymised sample + expected JSON
    └── ...                     # one test module per extractor
```

**Deviation from the prompt's `ingest/ classify/ extract/ …` top-level layout:** the same modules,
nested under `src/boq/` so the package is importable and testable, plus one addition — `text/`,
the positional-reconstruction layer, which the analysis showed is the foundation everything else
sits on. And `crosscheck/` is split out of `review/` because the checks are pure functions that
should run headless in CI, not only in the UI.

---

## 2. v1 schema

Written to `schema/project_quantities.v1.json` (JSON Schema draft 2020-12). It follows the
prompt's §5 item shape, with these additions, each earned by something in the sample:

| Addition | Why |
|---|---|
| `source.sheet` alongside `page` | Sheet numbers are **not unique** (`ST - 05` twice), so page index stays the key and sheet is an attribute |
| `source` allows `file_type: pdf \| xlsx \| dwf` and `cell` | Opening sizes come from a spreadsheet cell, not a page bbox |
| `null_reason` (required when `quantity` is null) | Guardrail §11.1 — "missing → null + reason" needs a field |
| `derived_from: [id]` | Steel derived from a schedule callout must point at it |
| `cross_checks: [{check_id, status, detail}]` | Attaches check results to the item, not just a panel |
| `review: {status, by, at, original_value}` | Audit trail from §7 |
| `method: extracted \| derived \| assumed \| unavailable` | Adds `unavailable` — PT slabs are not "assumed", they genuinely are not in the documents |

Wastage/lap multipliers are deliberately **not** in the item schema — per §5 they are applied at
reporting time only, and live in `config/factors.yaml`.

---

## 3. Assumptions I intend to make

Flagging these now, per §14.3. Each is configurable and none is baked into an extracted quantity.

**Extraction**

1. The title block is always the bottom strip of the sheet, with the static labels listed in
   analysis §2. If a future project moves it, classification fails loudly rather than guessing.
2. PDF reading order is never trusted; all table reads are positional.
3. A schedule appearing on more than one sheet must agree. Disagreement is an error, not a
   tie-break.
4. Mark sequences may have gaps (W04, W11, W12 are absent) and may carry A/B suffixes.
5. Spreadsheet error values (`#REF!` etc.) are missing data, never zero.

**Derivation** (all in `config/factors.yaml`)

6. Concrete wastage 5 %, rebar laps + wastage 8 %, blockwork 5 % — the prompt's defaults.
7. Steel unit masses: standard (Y8 0.395, Y10 0.617, Y12 0.888, Y16 1.579, Y20 2.466 kg/m).
8. Blocks per m² — **needs your number** (open question 4). No default will be invented.
9. Formwork = contact area excluding faces cast against earth or blinding.
10. Plaster area = wall area both faces, less openings; paint area = plaster area. Both `derived`.
11. Storey heights come from the thermal workbook (GF 4.48 m, FF 4.16 m, roof 3.20 m) since Set B
    does not state them; flagged as sourced from Set C.

**Explicit non-assumptions** — these will be `null` / `unavailable`, not estimated:

12. PT slab thickness, tendon count, strand length, anchorage count.
13. Strip-footing run lengths and beam sizes, until the DWF or vision path lands.
14. Any rate not present in `rates.yaml` — the item appears with quantity and a blank rate flagged
    "rate required".

---

## 4. Proposed change to the build order

One change, argued in analysis §11.3: **move the thermal workbook (Set C) parser from Phase 4 into
Phase 2**, alongside the PDF table extractors.

It is the only source of window and door dimensions and the best source of external wall areas,
so blockwork, plaster, paint and glazing in Phase 3 all depend on it. It is also the cheapest
extractor in the project — it is a spreadsheet. Leaving it in Phase 4 blocks Phase 3.

Everything else stays as written.

---

## 5. What I'd build first, once approved

Phase 0 scaffold, then the `text/` primitive with two regression tests that must pass before
anything else is written:

* the Set A page-5 area schedule reconstructs to the table in analysis §5.1, and all seven of its
  internal arithmetic identities hold;
* the Set B ST-02 column schedule reconstructs C1–C4 and BC with correct dimensions and bar
  callouts, from a page where document order is three disconnected runs.

Both are exact-value tests against the real sample, which is the honest measure of whether the
positional reader works.
