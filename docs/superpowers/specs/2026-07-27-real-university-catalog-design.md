# Real University Catalog — Design

**Date:** 2026-07-27
**Sub-project:** A — real catalog + contract v2.0.0. Sub-project B (Next.js UI)
has its own spec and depends on the contract settled here.
**Status:** design, approved

Originally scoped as one of three sub-projects, with C (scoring model reform)
sequenced between A and B. **MBTI has since been dropped by decision**, which
resolves the substance of C: the personality dimension is replaced by
self-reported culture preferences (below). C is therefore folded into A rather
than run separately, and B is unblocked because `Profile` is settled here once.

## Goal

Replace the synthetic university catalog with real universities, so UniMatch can
serve as an actual college-search tool rather than a demonstration of pipeline
mechanics.

Success: `universities` in Postgres holds 364 real institutions whose every
numeric field is either **observed from a citable source** or **null**. No field
is ever back-derived from another and presented as independent data.

## Governing principle

> A wrong number is worse than a null.

A null renders as "not available" and costs the user nothing. A plausible but
incorrect acceptance rate changes where a student applies. This principle
decides every open question below, and it is the reason several fields ship
empty rather than filled.

## Sources

Three tiers, merged in order. Later tiers never overwrite a higher-confidence
value; they only fill nulls.

### Tier 1 — UniMatch editorial baseline

Origin: `~/Claude/Projects/University_Recommendation_Project/js/data{,2,3,4}.js`
(a separate, earlier project by the same author). 364 institutions.

Provides, for every school: `name`, `loc`, `ctry`, `region`, `type`
(Public/Private), `size` (int), `setting`, `net` (net cost), **`gpa`**,
`strengths[]` (majors), and a 6-dimension `v` culture vector
(`collab, quirky, idealist, research, spirit, seminar`).

Two fields here exist in no public dataset and are the reason this tier is the
spine rather than a fallback:

- **`gpa`** — average admitted GPA. Not published at scale by anyone; US federal
  data does not carry it.
- **`v`** — the culture vector. Editorial, but it is the only structured
  campus-culture signal available, and sub-project C will likely rebuild the
  personality dimension on it.

The source file states plainly: *"Figures are approximate public-data estimates;
vibe ratings are editorial."* Everything from this tier is therefore tagged
provenance `editorial`.

A one-time converter extracts these records to `data-pipeline/sources/unimatch_364.json`,
which is committed and thereafter maintained in the repo. The build never parses
JavaScript, and the original project is read once and left untouched.

### Tier 2 — College Scorecard (US Dept. of Education)

**Use the bulk CSV, not the API.** The API requires a registered key, caps
`per_page` at 100, and limits to 1,000 requests/IP/hour. The bulk file requires
no key, no rate limit, and — decisively — provides the full institution universe
locally, which name matching needs.

```
https://ed-public-download.scorecard.network/downloads/Most-Recent-Cohorts-Institution_06102026.zip
```

23 MB zipped, 95 MB CSV, **6,273 institutions × 3,308 columns**, last updated
2026-06-10. Verified live and downloaded during design.

Columns consumed (verified present, with 1-based positions):

| Column | Pos | Maps to |
|---|---|---|
| `UNITID` | 1 | `id` |
| `INSTNM` | 4 | matching key |
| `CITY`, `STABBR` | 5, 6 | `location` |
| `CONTROL` | 17 | `type` cross-check |
| `ADM_RATE` | 37 | `acceptance_rate` |
| `SAT_AVG` | 60 | `avg_sat` |
| `UGDS` | 291 | `enrollment` (undergraduate) |
| `NPT4_PUB` / `NPT4_PRIV` | 317 / 318 | `net_price` (coalesced) |
| `TUITIONFEE_OUT` | 380 | `sticker_tuition` |

**The missing-value marker is the literal string `NA`**, not an empty cell. Any
parser that only checks for empties will silently read 100% coverage where the
truth is 16%.

National coverage is sparse — `SAT_AVG` 16%, `ADM_RATE` 30%, `NPT4_PUB` 28% —
but coverage *within this catalog* is high, because these 364 skew selective and
selective schools report. Measured against the 233 matched US schools:

| Field | Coverage of matched |
|---|---|
| `ADM_RATE` | 100% |
| `UGDS` | 100% |
| `TUITIONFEE_OUT` | 98% |
| `NPT4_PUB` + `NPT4_PRIV` | 98% combined |
| `SAT_AVG` | 84% |

`NPT4_PUB` and `NPT4_PRIV` are public/private variants of one measure — a school
has exactly one. They must be coalesced into a single `net_price`. `NPT4_PUB`
contains a small number of negative values (e.g. `-2296`); treat any value `<= 0`
as null.

### Tier 3 — Manual overrides (hand-curated, cited)

`data-pipeline/sources/manual_overrides.json`. Populated by a human, optionally
web-assisted. Every entry **must** carry a `source_url` and `retrieved` date; an
entry without them is a build error, not a warning.

```json
{ "University of Cambridge": {
    "acceptance_rate": {
      "value": 0.217,
      "metric_basis": "offers_over_applications",
      "cycle": "2025",
      "source_url": "https://www.undergraduate.study.cam.ac.uk/sites/default/files/2026-05/ug_admissions_statistics_2025_cycle.pdf",
      "retrieved": "2026-07-27" },
    "avg_sat": { "value": null, "status": "not_applicable", "note": "UK; SAT not used" } } }
```

The Cambridge figure above is verified from the primary source: 22,513
applications, 4,893 offers, 3,669 acceptances for the 2025 cycle.

**`metric_basis` is required on `acceptance_rate`.** Cambridge publishes both
offers (4,893) and acceptances (3,669). US `ADM_RATE` is admits ÷ applicants, so
the comparable figure is offers ÷ applications = 21.7%. Using acceptances instead
yields 16.3% and misrepresents the school as materially more selective. This is a
correctness requirement, not documentation.

## Rejected: automated web enrichment of the 90 non-US schools

Investigated during design and **rejected on evidence**:

- **Search summaries are unreliable.** Checked against primary sources twice,
  wrong both times. An Oxford acceptance rate was computed by dividing 2025
  admits by 2024 applications; Cambridge figures returned were from the 2022
  cycle, three years stale. Both looked authoritative.
- **Wikidata measures a different quantity.** One SPARQL query matched 78/90
  schools and returned 59 student counts — but `P2196` is *total* enrollment
  while `UGDS` is *undergraduate*. Median ratio to the editorial size is 1.16×,
  mean 1.34×, and up to 2.99× (HKUST 10,000 → 29,927; Fudan 15,000 → 44,300;
  Peking 16,000 → 44,730). Loading these into `enrollment` would corrupt the
  `size` band for 25% of the catalog, invisibly and in one direction.
- **Some institutions block automation.** `ox.ac.uk` returns 403 to both
  WebFetch and curl with a browser user-agent, on the asset host and the HTML
  page alike.
- **Some metrics do not exist.** Canadian universities, including Toronto,
  publish no institution-wide acceptance rate; admission is program-specific.

The 78 official website URLs from the Wikidata query are retained in
`data-pipeline/sources/wikidata_sites.json` as curation entry points for future
manual work. They are **not** a data source.

Consequence: non-US schools ship with `enrollment`, `avg_sat`, and usually
`acceptance_rate` null. That is the intended outcome.

## Schema and contract changes

`University` is contract-governed by `docs/contracts/score.schema.json`
(`$defs/University`, `additionalProperties: false`, all nine fields required).
These changes are therefore a **v1.0.0 → v2.0.0 bump**, applied in one change to
the contract plus both mirrors:

- `services/scoring-service/app/schemas.py`
- `services/recommendation-service/app/schemas.py`

Two contracts change, and they have different blast radii:

- **`score.schema.json` / `University`** — mirrored only in the two Python
  `schemas.py` files. The gateway does not mirror `University`.
- **`profile.schema.json` / `Profile`** — `mbti` removed (currently
  **required**), `culture_prefs` added. This **is** mirrored in
  `services/gateway/src/types.ts`, so the gateway changes too: delete
  `MBTI_REGEX` and the `mbti` field from `ProfileSchema`, add `CulturePrefsSchema`.

So all four artefacts move together in one change: the two schema files, both
Python mirrors, and the TypeScript mirror. Splitting the bump across changes is
contract drift (H3) and must halt the loop.

Tests asserting MBTI rejection must be replaced, not deleted, by tests asserting
the new validation: `services/gateway/test/routes.test.ts`
("rejects an invalid MBTI") and
`services/recommendation-service/tests/test_main.py::test_rejects_invalid_mbti`.
Removing a validation test without substituting an equivalent one weakens the
gate.

```
id               string        slug of the name — uniform across all 364
unitid           string | null NEW — federal UNITID where matched (US only)
name             string
country          string        NEW — gates whether tier 2 can apply at all
location         string
avg_gpa          number        tier 1 only; no public source has this
avg_sat          int | null    tier 2 SAT_AVG; never derived
acceptance_rate  number | null tier 2 ADM_RATE, or tier 3 with metric_basis
net_price        number | null coalesce(NPT4_PUB, NPT4_PRIV)  [renamed from `tuition`]
sticker_tuition  number | null NEW — TUITIONFEE_OUT
enrollment       int | null    NEW — UGDS, undergraduate only
size             enum          small | medium | large
majors           string[]
culture          object        NEW — the 6-dimension vector
provenance       object        NEW — per-field origin
```

### `tuition` → `net_price`

The current field is named `tuition` but tier 1 populates it from `net` (cost
after aid), and `_cost_fit` compares it against a `max_tuition` preference. Those
are different quantities, and conflating them misprices every school. Scorecard
supplies both separately, so the rename resolves it with real data. The
corresponding `Profile.preferences.max_tuition` rename is **deferred to
sub-project C**, since it changes the client contract and therefore the UI form.

### `size` derivation

`size` stays an enum because `_fit` compares it to `preferences.preferred_size`.
Derived from `enrollment` (UGDS) where available; otherwise from the tier-1
editorial `size` int. `enrollment` retains the raw number.

Thresholds: `<5,000` small, `<15,000` medium, else large. **These are proposed,
not inherited** — no current code derives a band from a headcount
(`generate.py` picks from `SIZES` at random; `scoring.py` only maps the enum to
`_SIZE_ORDER`). They should be sanity-checked against the real distribution once
tier 2 lands, since a US-centric cut may misband large non-US institutions.

### `provenance`

Per field, one of:

- `observed` — tier 2, a government statistical release
- `web_verified` — tier 3, carries `source_url` + `retrieved`
- `editorial` — tier 1, the author's estimate
- `not_applicable` — the measure does not exist for this institution
- `absent` — unknown

`not_applicable` is distinct from `absent` and load-bearing. All 90 non-US
schools get `avg_sat: not_applicable` (the SAT is not used outside the US), as do
the nine UC campuses and Caltech, which are **test-free**: UC Berkeley
"will not use SAT/ACT test scores regardless of whether or not they are
submitted." Marking these `absent` would invite a future contributor to "fix"
them by inventing numbers.

## Ingest pipeline

Network access is confined to one explicit, human-invoked step. Services and
tests never reach the network, preserving the offline-by-default rule.

```
data-pipeline/sources/
  unimatch_364.json        tier 1, committed
  scorecard_cache.json     tier 2, committed (filtered to matched schools)
  manual_overrides.json    tier 3, committed
  aliases.json             name → INSTNM overrides
  wikidata_sites.json      reference only, not a source
        │
        ├── build_catalog.py     --refresh is the ONLY networked path
        ▼
  out/universities.json    canonical; validates against score.schema.json v2.0.0
        │
        ├── load.py              existing loader, upsert on id
        ▼
     Postgres universities
        ▼
  recommendation-service/app/candidates.py   (unchanged)
```

The Scorecard cache is committed, filtered to matched schools only (a few hundred
rows, not 95 MB). This keeps builds reproducible and offline after first fetch,
and makes every observed number auditable in review.

### Name matching

Scorecard naming diverges from common usage in predictable ways: hyphens rather
than commas (`University of California-Berkeley`), campus qualifiers
(`Georgia Institute of Technology-Main Campus`), and your data uses an en-dash in
`University of Wisconsin–Madison`.

Normalization — lowercase, en/em-dash → hyphen, `", "` → `-`, strip
`-main campus`, drop `the`/`at`, strip non-alphanumerics — lifts exact matching
from 55% to **85% (233/274 US schools)**.

The remaining 41 are system/campus naming (`Columbia University in the City of
New York`, `University of Michigan-Ann Arbor`, `Rutgers University-New
Brunswick`) and go in `aliases.json`, curated by hand once. Fuzzy matching is
**not** used: at this scale a wrong automatic match is worse than a manual entry,
and 41 is a tractable afternoon.

Unmatched US schools after aliases are a **build warning listing each name**, so
the gap is visible rather than silent.

## Scoring changes

### Nullable `avg_sat`

`_academic_fit` currently reads `uni.avg_sat` unconditionally when `profile.sat`
is present. With nullable `avg_sat` it must skip the SAT term and fall back to
GPA-only — mirroring how it already handles a missing `profile.sat`. Required for
correctness, not an improvement.

`_cost_fit` reads the renamed `net_price`. No behavioural change.

### MBTI removed; culture preferences replace it

`mbti` is deleted from `Profile`, and `_personality_fit`, `_MBTI_SIZE_PREF` and
`_MBTI_STRUCTURE_PREF` are deleted from `scoring.py`. The rationale: that
dimension carried **0.20 of the score** while mapping `E/I` to campus size and
`J/P` to selectivity — inferences with no evidential basis, in a tool students
would act on.

The 0.20 weight transfers to a `culture` dimension driven by **self-reported
preference**. `Profile` gains an optional `culture_prefs` object over the same
six axes as the university `culture` vector:

| key | 0.0 | 1.0 |
|---|---|---|
| `collab` | Hyper-competitive | Collaborative & supportive |
| `quirky` | Work-hard, play-hard | Quirky & intellectual |
| `idealist` | Careerist / pre-professional | Idealist / mission-driven |
| `research` | Hands-on, project & co-op | Theory & research heavy |
| `spirit` | Low-key sports scene | Huge school spirit |
| `seminar` | Big lectures & autonomy | Small seminars & mentorship |

Scored by **preference-weighted agreement**, not cosine:

```
importance_k = |pref_k - 0.5| * 2        # 0 = indifferent, 1 = strong feeling
agreement_k  = 1 - |pref_k - culture_k|  # bipolar-correct; rewards low<->low
culture_fit  = sum(importance_k * agreement_k) / sum(importance_k)
             = 0.5 when every slider is centred (no preference expressed)
```

**Cosine is explicitly rejected.** These axes are bipolar: a student wanting a
competitive campus sets `collab = 0.0`, and against a hyper-competitive school
(`collab = 0.0`) cosine contributes `0 x 0 = 0` — scoring a perfect match no
better than a total mismatch. Cosine also cannot express indifference; the
midpoint is not "no opinion" to it. The reference implementation in the source
project uses cosine and inherits both faults, visible in its own reason-filter
which special-cases `|pref - 0.5| > 0.18`. The formula above encodes that
insight directly instead of patching around it.

Determinism is preserved: pure arithmetic, no clock, no randomness, no LLM.

### `culture` is required, not optional

Because the dimension is load-bearing, `University.culture` is **required** in
the contract, not nullable. Every one of the 364 schools has it from tier 1. A
school without a culture vector cannot be scored on 20% of the rubric and must
not enter the catalog.

## Testing

Offline and deterministic, consistent with the existing gates.

- **Fixtures, not fetches.** A ~20-row Scorecard fixture covering matched,
  unmatched, `NA`-valued, and negative-`NPT4` cases. No test touches the network.
- **`NA` handling** — asserts `NA` parses to null, not to a value or a crash.
- **Coalesce** — public school takes `NPT4_PUB`, private takes `NPT4_PRIV`,
  negative and `NA` both yield null.
- **Normalization** — the documented cases (`Berkeley`, `Wisconsin–Madison`
  en-dash, `-Main Campus`) map correctly.
- **No derived data** — a school with `NA` SAT ends with `avg_sat: null` and
  provenance `absent`/`not_applicable`, never a GPA-derived value. This guards
  the governing principle directly.
- **Tier precedence** — tier 3 fills nulls but never overwrites tier 2.
- **Override validation** — a tier-3 entry lacking `source_url` or `retrieved`
  fails the build; an `acceptance_rate` lacking `metric_basis` fails the build.
- **Contract** — every emitted record validates against `score.schema.json`
  v2.0.0; every school has a `culture` vector (required).
- **`culture_fit`** — the cases cosine gets wrong, asserted directly:
  - low↔low agreement scores high (`pref 0.0` vs `culture 0.0` → `1.0`), which
    is the bipolar bug and the reason cosine was rejected;
  - all sliders centred → exactly `0.5`, and no division by zero;
  - a single strong preference dominates a mismatched indifferent axis;
  - output stays within `[0, 1]` for all slider combinations.
- **No MBTI remains** — a grep gate asserting `mbti` appears nowhere in
  `scoring.py`, the schemas, or `types.ts`, so the dimension cannot be
  reintroduced silently.
- **Determinism** — same inputs produce a byte-identical `universities.json`;
  ordering is stable by `id`.

**`data-pipeline` currently has no coverage floor** — its `pyproject.toml` sets
no `addopts`, and `verify.sh` runs a bare `pytest -q`. This spec introduces one
at 80%, matching the two services, by adding
`--cov=. --cov-fail-under=80` to `[tool.pytest.ini_options]`. That is a new gate,
so it must be landed with the ingest code rather than assumed.

## Out of scope

- Any UI work — sub-project B, which has its own spec and consumes the contract
  settled here.
- The `Profile.preferences.max_tuition` → `max_net_price` rename. The
  *university* field is renamed here; the matching preference rename is deferred
  to B, where the form label and the field can change together. Until then
  `_cost_fit` compares `max_tuition` against `net_price` — the semantics are now
  correct even though the preference name still reads as sticker price.
- Hand-curating acceptance rates for the 90 non-US schools. Offered as an
  optional follow-up (the 20 UK schools are the tractable subset); not required
  for this sub-project to be complete.
- Field-of-study / CIP program data. The 38 `PCIP*` columns are percentages of
  degrees awarded, not a majors list, and tier 1 already supplies `strengths[]`.

## Open decisions

1. **Committing `scorecard_cache.json`.** Filtered it is small and makes builds
   reproducible offline; against that, it duplicates public data in the repo.
   *Recommendation: commit it*, for auditability and offline builds.
2. **Size-band thresholds** (see above) — confirm against the real distribution
   once tier 2 is loaded, rather than shipping the proposed US-centric cut
   unexamined.

Resolved during review: `id` is a slug for all 364 with `unitid` as a separate
nullable column, rather than a mixed-format key.
