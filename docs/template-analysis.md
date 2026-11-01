# Template Analysis — DCR2564 sample project

**Status:** analysis only. No extractor code has been written yet (per §14 of the build prompt).
**Sample project:** `DCR2564` — *Proposed Two Storey Villa*, Aali, Kingdom of Bahrain.
**Analysed on:** 2 August 2026.

This document records exactly how the DCR / Icon Engineering drawing template is laid out, and
which anchors the extractors will key on. Every claim below was verified against the supplied
files; where a number appears it was read out of the file, not assumed.

> **Note on what is still missing:** the build prompt asks for one complete sample project *plus its
> manually prepared BoQ*. The drawings and the thermal calculation arrived; **the manual BoQ did
> not**. Without it the Phase‑13 validation baseline cannot be built. Everything else in this
> document is complete. See [Open questions](#12-open-questions-for-you).

---

## 1. File inventory

| # | File | Role | Pages | Text layer | Notes |
|---|---|---|---|---|---|
| 1 | `DCR2564_FINAL_DRAWINGS.pdf` | **Set A** — Architectural + MEP | 28 | ✅ vector | A4 landscape (842×595 pt) |
| 2 | `STR2564.pdf` | **Set B** — Structural | 16 | ✅ vector | A2 landscape (1684×1191 pt = 594×420 mm) |
| 3 | `THERMAL_DCR2564.xlsx` | **Set C** — Thermal insulation calc | 11 sheets | ✅ native | EWA implementation form + working sheets |
| 4 | `DCR2564.pdf` | Set A, **municipality‑approved scan** | 8 | ❌ raster | Stamped `APPROVED`, CR 134432 |
| 5 | `DCR2564_______.pdf` | EWA Electricity & Meter Services Agreement | 1 | ❌ raster | Photo of a **handwritten** form |
| 6 | `DCR2564_FINAL_DRAWINGS_21.04.2026.dwf` | Set A source geometry | 28 sheets | vector (W2D) | AutoCAD Architecture 2025 |
| 7 | `DCR2564STR.dwf` | Set B source geometry | 16 sheets | vector (W2D) | from `STR2564-21.04.26.dwg` |
| 8 | `DCR2564_PLAN.dwf` | Set A subset | — | vector (W2D) | same sheet GUIDs as #6 |
| 9 | `DCR2564__ELEC.dwf` | Electrical | — | vector (W2D) | |

Both drawing PDFs are **fully vector with a real text layer on every page** (28/28 and 16/16).
No OCR is needed for the drawing sets. OCR/vision is needed only for files 4 and 5.

---

## 2. Title block anatomy

The title block is a fixed strip along the **bottom** of every sheet in both sets, occupying
roughly the bottom 14 % of the page. Field *labels* are static text and are byte‑identical on
every page, which makes them reliable anchors — the value sits in the cell adjacent to its label.

Labels present on every sheet, in both sets:

```
PROJECT NO:        PROJECT TITLE :    CLIENT   NAME   :   PROJECT LOCATION:
ZONING :           SHEET NO :         SHEET TITLE         SCALE:
DATE:              ARCHITECT:         A.CAD:              STRUCT. ENG.:
REVISIONS:  /  REV.  /  DESCRIPTION.  /  DATE.
```

Values for this project:

| Field | Set A value | Set B value |
|---|---|---|
| Project no | `DCR2564` | `DCR2564` |
| Header code | `AUO-DCR 2564` | `AUO-DCR 25564` ⚠ |
| Project title | PROPOSED TWO STOREY VILLA | PROPOSED TWO STOREY VILLA |
| Client | BALQEES MOHAMED MAHMOOD / SALWA AHMED SHAIKH KHALAF | same |
| Location / Zoning | AALI / RA | AALI / RA |
| Architect | MAHMOOD EBRAHIM | MAHMOOD EBRAHIM |
| A.CAD | S.AHMED ALMOSAWI | S.AHMED ALMOSAWI |
| Struct. eng. | S.ABBAS MARZOOQ | S.ABBAS MARZOOQ |
| Scale | AS SHOWN | AS SHOWN |
| Date | `APRIL-2026` | `APRIL-2025` ⚠ |
| Permit refs | `EPP/BN/232/AE/00002-C`, `EPP/BN/232/CE/00001-B` | same |
| Office block | ICON ENGINEERING / DCR Architects & Engineers, tel +973 381 64 381 | (Set B omits the office block) |

**Anchor rule:** locate the label string, then take the text whose bounding box is nearest to the
right of / below it within the title‑block strip. Do **not** rely on PDF reading order (see §4).

### 2.1 Sheet numbers

* **Set B:** the sheet number is in the text layer as `ST - 00` … `ST - 12` and extracts cleanly on
  all 16 pages. Note that **several Set B sheets are plotted with `/Rotate 270`**, ST-02 among
  them. PyMuPDF returns word coordinates in unrotated page space, so without applying the page
  rotation matrix a visual row arrives as a column and the title block appears on the left edge.
  `words_from_pdf` applies it by default, so a stored `bbox` means what an engineer sees.
* **Set A:** the sheet number is **not in the text layer at all**. Only the sheet *title* extracts.
  Page → sheet mapping for Set A must therefore come from the sheet title plus the index table on
  sheet A01 (or from the DWF manifest, §9).

⚠ **Sheet numbers are not unique.** In Set B, PDF pages 8 and 9 both carry `ST - 05`
(p8 = *Roof floor plan / upper roof framing layout*, p9 = *Typical structural details 1*). The DWF
manifest shows the same duplication one number earlier (`ST04 (2)` and `ST04`). The extraction
key must be **(file, page index)**, with the sheet number as a non‑unique attribute.

---

## 3. Sheet index

### Set A — 28 pages (titles extracted from the title block; numbers from the A01 index)

| Page | Sheet | Title | Discipline |
|---|---|---|---|
| 1 | A01 | Site development plan, location map, index | Architectural |
| 2–4 | N01–N03 | Net area plans | Architectural |
| 5 | N04 | **Area statement / area details** | Architectural |
| 6 | A02 | Ground floor plan | Architectural |
| 7 | A03 | First floor plan | Architectural |
| 8 | A04 | Roof floor plan | Architectural |
| 9 | A05 | Top roof plan | Architectural |
| 10 | A06 | Front and right elevation | Architectural |
| 11 | A07 | Rear and left elevation | Architectural |
| 12 | A08 | Boundary wall | Architectural |
| 13 | A09 | **Schedule of doors** | Architectural |
| 14 | A10 | **Schedule of windows** | Architectural |
| 15 | A11 | Section A‑A and stair details | Architectural |
| 16–20 | E01–E05 | Electrical layouts (GF, FF, roof deck, top roof, landscape) | Electrical |
| 21 | E06 | Electrical details & note | Electrical |
| 22–23 | P01–P02 | Plumbing / drainage layouts | Plumbing |
| 24–25 | WS01–WS02 | Water supply layouts | Plumbing |
| 26 | WS03 | Schematic water supply system | Plumbing |
| 27 | PD | Plumbing details | Plumbing |
| 28 | TI | Thermal insulation details + general notes | Thermal |

### Set B — 16 pages

| Page | Sheet | Title | Carries |
|---|---|---|---|
| 1 | ST‑00 | Cover sheet / list of structural drawings | — |
| 2–4 | ST‑01A/B/C | General structural notes, parts 1–3 | Materials, grades, **lintel table**, design summary |
| 5 | ST‑02 | **Foundation plan** | Footing schedule, column schedule, ground‑beam schedule, ground‑slab schedule |
| 6 | ST‑03 | Roof framing layout / first floor plan | Beam schedule |
| 7 | ST‑04 | Upper roof framing layout / second floor plan | Beam schedule |
| 8 | ST‑05 | Upper roof framing layout / roof floor plan | Beam schedule |
| 9 | ST‑05 ⚠ | Typical structural details 1 | Column schedule (repeat), footing schedule (repeat) |
| 10 | ST‑06 | Typical structural details 2 | Beam schedule (repeat), beam sections |
| 11 | ST‑07 | Typical structural details 3 | Strip‑footing details, boundary‑wall foundation, ground‑slab schedule |
| 12 | ST‑08 | Typical structural details 4 | Staircase details, entrance detail |
| 13 | ST‑09 | Typical structural details 5 | PT general notes, grouting, stressing sequence |
| 14 | ST‑10 | Typical structural details 6 | PT anchorage / tendon details |
| 15 | ST‑11 | Typical structural details 7 | Opening reinforcement details |
| 16 | ST‑12 | Typical structural details 8 | Basefill detail |

**Schedules repeat across sheets.** The column schedule and footing schedule each appear on two
sheets (ST‑02 and ST‑05); the beam schedule appears on four (ST‑03, ST‑04, ST‑05, ST‑06). The
extractor must deduplicate by schedule content, and treat a *disagreement* between two copies as
a hard error rather than picking one.

---

## 4. The single most important extraction finding

**PDF reading order is scrambled and must never be used.** These sheets are AutoCAD plots; text is
emitted in draw order, not layout order. The area schedule on page 5 of Set A reads like this in
document order:

```
170.8 SQ.M.  %  SQ.M.  TOTAL  406.9 SQ.M.  SQ.M.  89.8  %  132.5  SQ.M.  35.4  132.5  336.2
```

The same region, reconstructed by clustering words on their **y‑coordinate** and sorting by **x**,
is perfectly clean:

```
GROUND FLOOR   170.8 SQ.M.   35.4 %   132.5 SQ.M.
  1. MAIN VILLA  132.5 SQ.M.
  2. GARAGE      N/A
  3. SERVICES     38.3 SQ.M.
FIRST FLOOR    170.8 SQ.M.   41.3 %   154.6 SQ.M.
  1. VILLA       154.6 SQ.M.
  2. SERVICES     16.2 SQ.M.
ROOF DECK       65.3 SQ.M.   13.1 %    49.1 SQ.M.
  1. VILLA        49.1 SQ.M.
  2. SERVICES     16.2 SQ.M.
TOTAL          406.9 SQ.M.   89.8 %   336.2 SQ.M.
PLOT (LAND) AREA = 373.6 SQ.M.
```

So the foundation of every table extractor is: **take `page.get_text("words")`, bucket by rounded
y, sort each bucket by x.** `pdfplumber`'s ruling‑line table detection is a secondary strategy —
several of these schedules are drawn with polylines that do not form clean closed cells.

---

## 5. Set A — architectural content

### 5.1 Area schedule (page 5 / sheet N04) — fully extractable, self‑checking

| Floor | Built‑up (m²) | Municipal built‑up % | Net buildable (m²) |
|---|---|---|---|
| Ground floor | 170.8 | 35.4 | 132.5 |
| First floor | 170.8 | 41.3 | 154.6 |
| Roof deck | 65.3 | 13.1 | 49.1 |
| **Total** | **406.9** | **89.8** | **336.2** |

Plot (land) area **373.6 m²**.

Every arithmetic relation in this table closes exactly, which makes it an ideal regression fixture:

* `132.5 + 38.3 = 170.8` (GF: main villa + services; garage N/A) ✅
* `154.6 + 16.2 = 170.8` (FF) ✅
* `49.1 + 16.2 = 65.3` (roof deck) ✅
* `170.8 + 170.8 + 65.3 = 406.9` ✅
* `132.5 + 154.6 + 49.1 = 336.2` ✅
* `35.4 + 41.3 + 13.1 = 89.8` ✅
* Each percentage is that floor's net buildable ÷ plot area, **truncated** to 1 dp ✅

**Correction (established while implementing the checker):** an earlier draft of this document
said the office *rounds* these percentages. It does not — it **truncates**, and the total is the
sum of the truncated values:

| Floor | net ÷ plot | rounded | truncated | printed |
|---|---|---|---|---|
| Ground | 35.4657 % | 35.5 ✗ | **35.4** | 35.4 |
| First | 41.3812 % | 41.4 ✗ | **41.3** | 41.3 |
| Roof deck | 13.1424 % | 13.1 | **13.1** | 13.1 |
| Total | 89.9893 % | 90.0 ✗ | sum = **89.8** | 89.8 |

Rounding is wrong on two of the three floors, and recomputing the total directly is wrong too.
A checker that rounds raises three false cross-check failures on a perfectly consistent sheet.
This convention is recorded in `config/factors.yaml` and locked by a regression test.

### 5.2 Door and window schedules (pages 13–14) — partially extractable

These are **not tables**. Each mark is a *card*: a small elevation drawing with a four‑line text
block beside it.

```
DOOR MARK:  D04
LOCATION:   BEDROOM + KITCHEN
QUANTITY:   9
DESCRIPTION: SINGLE WOOD DOOR (REFER TO MANUFACTURER'S DETAIL).
```

Extractable per card: **mark, location, quantity, description** (which carries material and
glazing — e.g. *"24mm THK DOUBLE GLAZED"*, *"SINGLE WOODEN DOOR"*).

**Not extractable: width and height.** There is not a single dimension string in the text layer of
either page — the sizes exist only as dimension graphics on the card elevations. This is the
central limitation of Set A.

Doors — 10 marks, **22 leaves**:

| Mark | Location | Qty | Type |
|---|---|---|---|
| GD01 | Main gate | 1 | Double leaf single swing aluminium glass |
| GD02 | Garage | 1 | Automated roll‑up, by specialist |
| D01 | Main entrance | 1 | Single wooden |
| D02 | Kitchen entrance | 1 | Single wooden |
| D03 | Kitchen | 1 | 24 mm double glazed, aluminium frame |
| D04 | Bedroom + kitchen | 9 | Single swing panel |
| D05 | Hall bathroom | 1 | Single wood |
| D06 | Ventilation | 1 | 24 mm double glazed |
| D07 | Bathroom | 5 | 24 mm double glazed |
| SD01 | Dining & sitting | 1 | 24 mm double glazed 3‑panel sliding |

Windows — 14 marks, **22 units**: W01 ×2, W02 ×3, W03 ×2, W05 ×1, W06 ×2, W07 ×1, W08 ×1,
W09 ×1, W10 ×2, W13 ×1, W14 ×1, W15 ×1, W16 ×2, W17 ×2. All are 24 mm double‑glazed.
Marks **W04, W11 and W12 do not exist** in the set — the numbering has gaps, so an extractor must
not assume a contiguous mark sequence.

### 5.3 Room schedule

There is **no room finishes schedule** in this set. Room names and sizes are annotation text on the
floor plans, in the form `4.9X3.53M` / `BEDROOM1-`, `1.74X3.3M` / `BATH`. Room name and nominal
size are recoverable by pairing each `<num>X<num>M` string with the nearest text label, but this is
plan‑annotation mining, not schedule parsing — lower confidence, and it gives *nominal* room
dimensions rather than net areas. Finishes are called out on the elevations as `PAINT-1`,
`PAINT-2`, `PORCELAIN-2` with no area quantification.

### 5.4 General notes (page 28)

Machine‑readable and directly relevant to blockwork and thermal take‑off:

* All external walls shall be approved **insulated blocks** unless otherwise specified.
* All external walls including shaft walls shall receive an approved thermal insulating system.
* **Parapet walls shall be normal blocks** unless otherwise specified.
* All exterior windows shall be approved insulated **double glazing**.
* All enclosed room projection bottom slabs shall have thermal insulation.

---

## 6. Set B — structural content

### 6.1 Column schedule (ST‑02, repeated on ST‑05)

| Mark | b (mm) | d (mm) | Vertical bars | Links @ support | Links @ midspan |
|---|---|---|---|---|---|
| BC | 200 | 300 | 6 Y12 | T8 @ 200 c/c | T8 @ 200 c/c |
| C1 | 200 | 400 | 6 Y16 | T8 @ 100 c/c | T8 @ 200 c/c |
| C2 | 200 | 500 | 8 Y16 | 2T8 @ 100 c/c | 2T8 @ 200 c/c |
| C3 | 200 | 600 | 12 Y16 | 2T8 @ 100 c/c | 2T8 @ 150 c/c |
| C4 | 300 | 600 | 16 Y20 | 2T10 @ 100 c/c | 2T10 @ 150 c/c |

⚠ In document order this schedule is emitted as three disconnected runs — all the bar callouts,
then all the marks, then all the dimensions. It is **only** reconstructable positionally. This is
the sharpest example of why §4 matters.

**Correction.** The table above was rewritten after the extractor was built against the real
sheet. The first draft of this document, written before per-word coordinates were available,
assigned **C1, C3 and BC to each other's sections** — it listed C1 as 200×600/12 Y16 (that is
C3), C3 as 200×300/6 Y12 (that is BC), and BC as 200×400/6 Y16 (that is C1). The reading-order
text gives no reliable mark-to-value association, and the inference drawn from it was wrong.

The error mattered. With the plan counts in §6.6, pricing C1 as 200×600 overstates each C1 by
50 %, and C3 as 200×300 understates each C3 by 50 %. Overall column cross-section is only about
4 % out, because the errors partly offset — but columns are ordered and priced *per type*, so
the per-type figures are what a supplier quotes against.

The values above are now produced by `extract/structural/column_schedule.py` and pinned by
exact-value tests. A sixth row — the ground slab schedule `GS-1`, which sits immediately to the
right of C4 — is correctly excluded; an unbounded outer column band absorbed it at first.

### 6.2 Footing schedule (ST‑02, repeated on ST‑05)

| Mark | L | B (mm) | D (mm) | Bottom main | Bottom transv. | Top main | Top transv. | Remarks |
|---|---|---|---|---|---|---|---|---|
| SF1 | SEE PLAN | 1000 | 400 | 6T16 | T16 @ 150 | – | – | Concentric |
| SF2 | SEE PLAN | 1200 | 400 | 8T16 | T16 @ 150 | – | – | Concentric |
| SF3 | SEE PLAN | 1000 | 400 | 6T16 | T16 @ 150 | 6T16 | T16 @ 150 | Eccentric |
| SF4 | SEE PLAN | 500 | 400 | 6T16 | T16 @ 150 | 6T12 | T12 @ 150 | Eccentric |

These are **strip footings**, and `L = SEE PLAN`. Footing concrete volume therefore **cannot** be
computed from the schedule alone — the run lengths must come from the plan geometry. This is the
principal blocker for substructure concrete, and the strongest argument for the DWF path (§9).

### 6.3 Ground beam schedule (ST‑02)

| Mark | b (mm) | d (mm) | Top | Bottom | Stirrups @ supp. | @ mid | Location |
|---|---|---|---|---|---|---|---|
| GB‑1 | 200 (200/300 on the second copy ⚠) | 400 | 4‑Y16 | 4‑Y16 | R8 @ 120 | R8 @ 150 | Strip foundation outside villa |
| GB‑2 | 200 | 400 | 4‑Y16 | 4‑Y16 | R8 @ 120 | R8 @ 150 | On filled block |
| GB‑3 | 200 | 400 | 4‑Y16 | 4‑Y16 | R8 @ 120 | R8 @ 150 | Strip foundation inside villa |
| GB‑4 | 200 | 500 | in section | in section | R8 @ 120 | R8 @ 150 | Boundary wall foundation |

⚠ Sheet ST‑02 carries the ground‑beam schedule **twice**, and the two copies disagree: GB‑1 is
`200` wide in one and `200 / 300` in the other, and the location text differs
(*"in strip foundation outside villa"* vs *"in strip Top of foundation level"*). This must be
raised as a cross‑check failure, not silently resolved.

### 6.4 Beam schedule (ST‑03, ‑04, ‑05, ‑06)

| Mark | Bottom bars | Top continuous | Extra at support | Stirrups @ supp. | @ mid |
|---|---|---|---|---|---|
| B1 | 4 Y16 | 2 Y16 | shown in plan | Y8 @ 200 | Y8 @ 200 |
| B2 | 4 Y16 | 4 Y16 | shown in plan | Y8 @ 150 | Y8 @ 150 |
| B3 | 4 Y20 | 4 Y20 | shown in plan | Y8 @ 150 | Y8 @ 150 |

Beam **sizes are not in the schedule** — the width/depth are annotated on the framing plans, and
extra bars are "shown in plan". Beam concrete and steel are therefore plan‑dependent, like footings.

### 6.5 Slabs

* `GS-1` — 100 mm thick solid ground slab with BRC A142 mesh.
* `GS-2` — 300 mm thick solid slab with Y16 @ 200 c/c top and bottom.
* Suspended slabs at first floor, second floor and roof are all annotated
  **`POST-TENSION SLAB — BY PT SPECIALIST`**, and every framing sheet carries the warning
  `DESIGN MUST BE REVIEW AFTER PT DESIGN`.

**Consequence: there are no PT quantities in this set.** No tendon count, no strand length, no
anchorage count, no slab thickness on the structural sheets. Per guardrail §11.1 these must be
emitted as `null` with reason `"PT design by specialist — not in issued drawings"`. (The thermal
workbook independently assumes a 200 mm slab and 500 mm beams; see §7.4. That is an *input
assumption of a different document*, not a structural quantity, and must not be promoted to one.)

### 6.6 Element counts from the foundation plan

Counting mark text positionally on ST‑02 works, with one trap. Sheet ST‑02 carries **two plans**
(foundation plan, and columns & beams plan) plus the schedule legends. A naive count of `C1…C4`
strings returns 44; the true figure is 20 per plan.

After separating the legend (x < 447 pt) and splitting the two viewports on the y gap at ≈ 850 pt:

| | Foundation plan | Columns & beams plan |
|---|---|---|
| C1 | 4 | 4 |
| C2 | 9 | 9 |
| C3 | 5 | 5 |
| C4 | 2 | 2 |
| **RC columns** | **20** | **20** |
| BC (boundary columns) | 13 | 13 |
| SF1 / SF2 / SF3 / SF4 | 2 / 6 / 5 / 4 = **17** | — |

The two plans agree exactly on column counts — a free, genuine cross‑check. **20 RC columns +
13 boundary columns; 17 strip‑footing runs.**

### 6.7 Other structural data available

* Lintel table (ST‑01B), expansion‑joint locations and detail (ST‑07), staircase reinforcement
  (ST‑08: Y16 @ 150 and Y12 @ 150 c/c, tread 300 / riser 160 from Set A page 15).
* Boundary wall foundation: 8‑Y12Ø, R8 @ 200 c/c stirrups, 75 mm blinding, Y12 @ 200 c/c,
  blockwork 200 or 150 mm thick with first two courses filled with mortar.
* Blinding: 75 mm thick, with 1000 gauge polythene sheet and two coats of bituminous paint
  (1000 microns).

---

## 7. Set C — thermal calculation (`THERMAL_DCR2564.xlsx`)

11 sheets. This is the **richest single file in the project** and the only source for opening sizes.

### 7.1 Headline figures (sheet `DETAILS OF GLASS SELECTED`)

| Quantity | Value |
|---|---|
| Total glass area | **146.93 m²** |
| Total surface (wall) area | **814.816 m²** |
| Glazing ratio | **18.03 %** |
| Glass spec | SunGuard® Solar outer / HP Clear DGU inner, 6 mm + 12 mm air + 6 mm |
| Summer U‑value | 1.6 W/m²·°C, SC 0.21, light transmittance 30 % |
| Curtain wall / skylight | none |

### 7.2 Envelope U‑values

| Element | Build‑up | U‑value (W/m²·°C) | Area (m²) |
|---|---|---|---|
| Roof | 4 mm waterproofing membrane, 75 mm lightweight screed, **75 mm ISO FOAM**, 150 mm precast slab | **0.26** | — |
| External walls | 15 mm plaster, **200 mm Sandwich Block (Al Manaratain)**, 15 mm plaster | **0.54** | **529.606** |
| External columns | 200 mm RC, **50 mm extruded polystyrene**, gypsum board, plaster | **0.50** | **98.4** |
| External beams | 200 mm RC, **50 mm extruded polystyrene**, gypsum board, plaster | **0.50** | **39.88** |
| Ceilings over non‑AC space | 150 mm precast slab, 50 mm XPS, gypsum board | **0.49** | 0 |

The declared compliance basis is **Thermal Insulation Order no. 8/99**. Per prompt §10 the code
limits must be read from the file and validated against the configured code version — the limits
themselves are not stated numerically in this workbook, only the achieved U‑values, so the
comparison values will have to come from configuration and the mismatch flagged.

### 7.3 Wall areas by elevation (sheets `wall`, `Main`)

| Floor | Height (m) | Front | Rear | Left | Right |
|---|---|---|---|---|---|
| Ground | 4.48 | 15.0 m | 15.7 m | 23.9 m | 24.3 m |
| First | 4.16 | 15.0 m | 15.7 m | 23.9 m | 24.3 m |
| Roof | 3.20 | 7.8 m | 7.8 m | 13.0 m | 13.0 m |
| **Area total** | | **154.560** | **160.608** | **248.096** | **251.552** |

Sum = **814.816 m²**, matching §7.1. Parapet is excluded by the form's own instruction.
This gives us external wall area per elevation per floor **directly** — the blockwork extractor's
best input, far better than anything derivable from Set A.

### 7.4 Opening schedule with sizes (sheet `Main`) — the key finding

Sheet `Main` is the only place in the entire project where **window and door dimensions exist**:

| Mark | W × H (m) | Front | Rear | Left | Right | Area (m²) |
|---|---|---|---|---|---|---|
| W1 | 0.5 × 1.5 | 1 | | | | 0.750 |
| W2 | 0.7 × 2.8 | | | 1 | 2 | 5.880 |
| W3 | 0.6 × 1.5 | 1 | | | 1 | 1.800 |
| W5 | 3.3 × 7.0 | | 1 | | | 23.100 |
| W6 | 4.3 × 2.8 | | | 1 | 1 | 24.080 |
| W7 | 4.4 × 2.8 | 1 | | | | 12.320 |
| W8A | 3.0 × 2.8 | 1 | | | | 8.400 |
| W8B | 0.9 × 2.8 | | | | 1 | 2.520 |
| W9A | 3.4 × 2.8 | 1 | | | | 9.520 |
| W9B | 0.9 × 2.8 | | | 1 | | 2.520 |
| W10 | 1.6 × 2.8 | 2 | | | | 8.960 |
| W13 | 0.8 × 1.5 | | | 1 | 1 | 2.400 |
| W14 | 0.4 × 1.4 | | | | 1 | 0.560 |
| W15 | 1.0 × 1.4 | | | | 1 | 1.400 |
| W16 | 1.1 × 1.4 | | | 2 | 1 | 4.620 |
| W17 | 4.3 × 2.8 | | | | 1 | 12.040 |
| D1 | 1.3 × 3.0 | 1 | | | | 3.900 |
| D2 | 1.0 × 3.0 | 1 | | | | 3.000 |
| D3 | 1.0 × 3.0 | 1 | | | | 3.000 |
| D6 | 1.6 × 2.4 | | | | 1 | 3.840 |
| SD1 | 4.4 × 2.8 | 1 | | | | 12.320 |
| | | | | | **Total** | **146.930** |

Recomputing independently from W × H × count reproduces **146.930 m²** exactly, matching the
declared total. The glazing figure is sound.

⚠ **Label defect in the `window` sheet.** The `window` sheet mirrors `Main`, but from the W13 row
onward its column‑A *labels* are shifted one row against the dimension rows: `W13` is missing, the
row carrying 0.8 × 1.5 is labelled `W14`, and so on, ending with `D6` appearing twice. The
**dimensions, counts and totals are unaffected** — the total is still 146.930 m² — so this is a
labelling defect, not a quantity error. But it means the `window` sheet **cannot** be used to map
glass area back to a window mark. **Read openings from `Main`, never from `window`.**

### 7.5 The envelope decomposes exactly — and it settles the blockwork area

Found while building the Phase 3 rules engine. The four envelope components sum to the
declared total surface area with no residual at all:

| Component | Source | Area (m²) |
|---|---|---|
| Glass | `DETAILS OF GLASS SELECTED` E11 | 146.930 |
| Opaque external wall | `WALLS` G14 | 529.606 |
| External columns | `COLUMNS` G14 | 98.400 |
| External beams | `BEAM ` H14 | 39.880 |
| **Sum** | | **814.816** |
| **Declared total** | `DETAILS OF GLASS SELECTED` H11 | **814.816** |

Exact to nine decimal places. This matters for more than tidiness: it proves the stated wall
area of **529.606 m² is already net of openings, columns and beams**.

That is the authoritative blockwork area. The obvious take-off move — start from the 814.816 m²
gross envelope and deduct openings — would be wrong twice over: it would leave the columns and
beams in, and if openings were deducted from the 529.606 m² figure as well, blockwork would be
understated by 146.93 m², about **28 %**. This is now the `envelope_decomposition` cross-check.

### 7.6 Broken formulas

Sheet `CAL BEAMS` contains live `#REF!` errors in cells `E13`, `K13`, and in the totals row
`E40` and `K40` ("Total Area of BEAM", front and right elevations). Any reader of this workbook
must detect `#REF!`/`#VALUE!`/`#DIV/0!` and refuse the cell — never coerce it to zero. The beam
areas for the front and right elevations are consequently **unknown** in this file, even though
the `BEAM` sheet quotes a total beam area of 39.88 m².

---

## 8. Cross‑checks this sample makes possible

The prompt (§7) asks for a cross‑check panel. This project supports these, and several already
fail — which is exactly the point of building the panel:

| # | Check | Result on DCR2564 |
|---|---|---|
| 1 | Area table internal arithmetic | ✅ closes exactly (§5.1) |
| 2 | Net buildable % vs plot area | ✅ (using rounded components) |
| 3 | Column count: schedule vs plan | ✅ 20 on both plans (§6.6) |
| 4 | Glass area: declared vs recomputed from `Main` | ✅ 146.930 = 146.930 |
| 5 | Wall area: `wall` sheet vs `DETAILS OF GLASS SELECTED` | ✅ 814.816 both |
| 5a | **Envelope decomposition**: glass + wall + columns + beams = total surface | ✅ exact (§7.5) — establishes the net blockwork area |
| 6 | Window **count**: Set A schedule vs Set C | ❌ **fails** — 22 vs 24, but see the correction below: **six marks disagree**, not two |
| 7 | Window **marks**: Set A vs Set C | ⚠ Set A has no W04/W11/W12; Set C has no W4/W11/W12 either — consistent gap, but Set C adds A/B suffixes |
| 8 | Glazed doors: Set A vs Set C | ✅ Set C counts only glazed leaves (D1, D2, D3, D6, SD1) — consistent with Set A's descriptions |
| 9 | Built‑up area vs sum of slab areas | ❌ not possible — PT slabs by specialist, no slab areas issued |
| 10 | Blockwork vs external wall perimeter × height − openings | ✅ possible from §7.3 minus §7.4 |
| 11 | Ground‑beam schedule: ST‑02 copy 1 vs copy 2 | ❌ **fails** — GB‑1 width 200 vs 200/300 (§6.3) |
| 12 | Slab spec: structural vs thermal | ❌ **fails** — structural says PT slab (thickness not issued); thermal assumes 150 mm precast slab (roof) and 200 mm slab (`Main`) |
| 13 | Project identifier consistency | ❌ **fails** — five renderings: `DCR2564`, `AUO-DCR 2564`, `AUO-DCR 25564`, `DCR2503` (thermal form), `DCR2554` (EWA form) |
| 14 | Title‑block date consistency | ❌ **fails** — Set A `APRIL-2026`, Set B `APRIL-2025` |
| 15 | Sheet number uniqueness | ❌ **fails** — `ST - 05` used twice (§2.1) |

Checks 11–15 are all real defects in the issued documents. A tool that surfaces these at
take‑off time is worth having independently of the quantities.

### 8.1 Correction — the window counts do not reconcile

An earlier draft of this document recorded check 6 as *reconcilable*: Set A totals 22 window
units, Set C totals 24, and Set C splits `W08` into `W8A`/`W8B` and `W09` into `W9A`/`W9B`,
which appeared to account for the difference of two.

**That was wrong, and it was wrong in the most dangerous way — it looked right at the total.**
Comparing mark by mark, with padding normalised (`W01` ≡ `W1`) and split leaves folded back
onto their base mark:

| Mark | Set A | Set C | |
|---|---|---|---|
| W1 | 2 | 1 | ❌ |
| W2 | 3 | 3 | ✅ |
| W3 | 2 | 2 | ✅ |
| W5 | 1 | 1 | ✅ |
| W6 | 2 | 2 | ✅ |
| W7 | 1 | 1 | ✅ |
| W8 | 1 | 2 | ❌ |
| W9 | 1 | 2 | ❌ |
| W10 | 2 | 2 | ✅ |
| W13 | 1 | 2 | ❌ |
| W14 | 1 | 1 | ✅ |
| W15 | 1 | 1 | ✅ |
| W16 | 2 | 3 | ❌ |
| W17 | 2 | 1 | ❌ |
| **Total** | **22** | **24** | |

**Six of fourteen marks disagree.** The totals differ by only two because the errors partly
cancel: W1 −1 and W17 −1 offset W13 +1 and W16 +1, leaving the W8 and W9 splits as the visible
net. The two sets genuinely disagree about how many of six window types the villa has, which
matters for both the glazing cost and the window order.

The lesson is now a design rule in `crosscheck/checks.py`: **compare item by item, never by
total.** A totals-only comparison reports this as reconciled and hides all six.

---

## 9. The DWF option

The `.dwf` files are standard Autodesk ePlot packages (ZIP containers holding `manifest.xml`,
per‑sheet `descriptor.xml`, and binary `.w2d` WHIP geometry streams). They are worth taking
seriously:

* **Sheet identity comes free.** `manifest.xml` lists layout names directly —
  `STR2564-21.04.26-ST00 … ST12` — no classifier needed, and it independently confirms the
  duplicate sheet number.
* **Units are declared.** Each descriptor states `_UnitLinear = millimeter`,
  `_UnitArea = square_meters`, paper `594 × 420 mm`, and the source file
  (`STR2564-21.04.26.dwg`, AutoCAD Architecture 2025).
* **Geometry is vector and to scale**, which is the only path to the two quantities Set B cannot
  give us: **strip‑footing run lengths** (§6.2) and **beam sizes/lengths** (§6.4).

The cost is that `.w2d` is a compressed binary opcode stream with no maintained Python reader —
writing one is a real piece of work, not a library call. **Recommendation: treat DWF as a
Phase‑3.5 accuracy upgrade, not a Phase‑0 dependency.** Use `manifest.xml` immediately (it is
plain XML and gives free sheet classification); defer `.w2d` geometry until the table extractors
are proven.

---

## 10. Extraction feasibility summary

| Quantity | Source | Feasible? |
|---|---|---|
| Per‑floor / built‑up / plot areas | Set A p5 | ✅ high confidence, self‑checking |
| Column schedule + counts | Set B ST‑02 | ✅ high confidence |
| Footing schedule (sections, rebar) | Set B ST‑02 | ✅ sections yes |
| Footing **volume** | needs run lengths | ❌ `L = SEE PLAN` — DWF or vision |
| Ground‑beam / beam sections | Set B | ⚠ ground beams yes; beams have no sizes in schedule |
| Beam **volume** | needs plan sizes + lengths | ❌ DWF or vision |
| Ground slab (GS‑1/GS‑2) | Set B ST‑02/ST‑07 | ✅ spec; area needs plan |
| Suspended slab / PT | — | ❌ **by specialist — emit `null`** |
| Reinforcement | schedules, no BBS | ⚠ derivable per element, must be flagged `derived` |
| External wall area | Set C `wall` | ✅ **excellent** — per elevation, per floor |
| Blockwork / thermal block | Set C + notes | ✅ wall area − openings, × block factor |
| Glazed area | Set C `Main` | ✅ 146.93 m², independently verified |
| Door/window marks, qty, type | Set A p13–14 | ✅ |
| Door/window **sizes** | Set C `Main` only | ⚠ only via Set C — not in Set A |
| Insulation areas & U‑values | Set C | ✅ |
| Room names / nominal sizes | Set A plan annotation | ⚠ annotation mining, medium confidence |
| Finishes areas | — | ❌ no finishes schedule exists |
| Plaster / paint areas | — | ⚠ derivable from wall areas, `derived` |
| Electrical point counts | Set A E01–E06 | ⚠ symbol counting, Phase 7 |
| Electrical loads | EWA form (file 5) | ⚠ **handwritten photo** — vision, low confidence, never authoritative |
| Sanitary fixtures / pipe runs | Set A P/WS sheets | ⚠ Phase 7 |

---

## 11. Implications for the build

1. **Positional text reconstruction is the core primitive**, not table detection. Build it first,
   test it against the page‑5 area schedule and the ST‑02 column schedule.
2. **No OCR is needed for the drawing sets.** Budget vision for: door/window card dimensions,
   plan geometry (footing runs, beam sizes), MEP symbol counting, and the two scanned files.
3. **Set C is a first‑class input, not an afterthought.** It is the sole source of opening sizes
   and the best source of wall areas. It should be parsed in Phase 2 alongside the PDF schedules,
   not deferred to Phase 4 as the build order currently implies. *This is the one change I'd
   propose to the phase ordering.*
4. **Spreadsheet error handling is a hard requirement.** `#REF!` cells are present in the real
   sample. Read with `data_only=True`, and treat any error string as a missing value with a reason.
5. **Repeated schedules must be reconciled, not deduplicated blindly** — the GB‑1 disagreement
   would be silently lost by a "take the first copy" rule.
6. **Counting requires viewport separation.** Sheets carry multiple plans plus legend copies of
   the same marks; cluster before counting (§6.6).
7. **PT is out of scope for extraction on this project type** and must be reported as such.

---

## 12. Open questions for you

1. **The manually prepared BoQ for DCR2564 was not supplied.** Could you send it? Without it there
   is no validation baseline, and prompt §13 asks for three such projects.
2. **Opening sizes:** confirm that reading window/door dimensions from the thermal workbook
   (`Main` sheet) is acceptable practice in your office, or whether they should always be
   read off the Set A schedule cards by vision and cross‑checked against Set C.
3. **PT slabs:** for estimating, do you want a *configurable assumed* PT slab thickness and
   tendon rate (clearly flagged `assumed` and sheeted separately), or a hard `null`? The guardrails
   say never estimate silently — an explicit, labelled assumption would satisfy that, but it is
   your call.
4. **Blocks per m²:** what factor does the office use for 200 mm Sandwich Block, and for 100/150 mm
   internal blocks?
5. **Set B has no bar bending schedule.** Confirm rebar should be derived from schedule callouts
   and flagged `derived`, with your standard lap/wastage default of 8 %.
6. Is the `DCR2503` application number on the thermal form a typo for `DCR2564`, or a genuinely
   different EWA application?
