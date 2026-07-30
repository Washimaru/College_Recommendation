# Explore & Decide Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let a student go from a blank form to a rated, saved list of universities they intend to apply to, comparing candidates side by side, without losing their work.

**Architecture:** Contract v4.0.0 carries region, setting, institution type, student-body composition and two official URLs through the existing three-tier catalog build. Region and setting fold into the existing `fit` scoring dimension as soft preferences; institution type joins `scope` as a hard pre-ranking filter. The frontend splits from one 443-line page into four routes sharing a `localStorage`-backed profile context.

**Tech Stack:** Python 3.11 + FastAPI + Pydantic v2 (scoring-service, recommendation-service, data-pipeline) · Node 20 + TypeScript + Fastify (gateway) · Next.js 16 App Router + React 19 + Tailwind 4 (college-recommender) · Postgres 16 · pytest, vitest

## Global Constraints

- Spec: `docs/superpowers/specs/2026-07-29-explore-and-decide-design.md`
- Contract version is exactly `4.0.0`. Four artefacts move in the same commit: `docs/contracts/{profile,score,recommendation}.schema.json`, `services/scoring-service/app/schemas.py`, `services/recommendation-service/app/schemas.py`, `services/gateway/src/types.ts`. Splitting them is contract drift (H3) and must halt work.
- A missing value is `null`. Never derive it, never default it to zero. `provenance` records the origin.
- `University.location` is display-only. It must never be a filter or a scoring input.
- `population` is absent for non-US schools, with `provenance.population` set to `not_applicable`.
- Python: type hints everywhere, `ruff` clean (line length 100), pytest. TypeScript: `strict`, no `any` in exported signatures, vitest.
- Coverage floors: 80% for both Python services (`--cov-fail-under=80` in their `addopts`), 70% lines/functions/branches/statements for the gateway and the UI. **`data-pipeline` has no coverage floor** — its `pyproject.toml` sets no `addopts`, so a narrowed run there needs no `--no-cov`.
- Run `PYBIN=.venv/bin/python ./scripts/verify.sh` from the repo root after any Python or gateway change. It must print `VERIFY: GREEN`.
- The gate's `ruff` steps end in `|| true` and gateway `eslint` is not in the gate at all. Lint must be run explicitly: `.venv/bin/python -m ruff check .` per Python project, `npx eslint app lib components` in `college-recommender`.
- The 15–20% safety band is a stated preference, not a measured finding. Copy must present it as a suggestion.
- Docker must be running for `smoke.sh`: `open -a Docker`, then `docker compose up -d`.

---

## File Structure

**Data pipeline**
- Modify `data-pipeline/build_catalog.py` — `enrich()` carries six new fields; `CACHED_COLUMNS` gains five Scorecard columns; new `extract_population()`.
- Modify `data-pipeline/load.py` — six new columns in the upsert.
- Modify `db/schema.sql` — six new columns.
- Modify `data-pipeline/tests/test_build_catalog.py` — new test classes.

**Contracts and services**
- Modify all three `docs/contracts/*.schema.json` — v4.0.0.
- Modify both `app/schemas.py` mirrors — `University` gains six fields, `Preferences` swaps `locations` for `regions`/`settings`/`institution_type`, `Activity` gains `description`.
- Modify `services/scoring-service/app/scoring.py` — `_fit` scores region and setting; export `classify_activity`.
- Modify `services/recommendation-service/app/candidates.py` — `in_scope` gains institution-type filtering.
- Modify `services/recommendation-service/app/main.py` — apply the type filter; add `POST /activities/classify`.
- Modify `services/gateway/src/{types.ts,routes.ts,clients/recs.ts}` — mirror plus proxy route.

**Frontend** — `app/page.tsx` is 443 lines and holds the form, results, sort, filters, modal state and tab switching. It splits:

- Create `college-recommender/lib/profileStore.tsx` — context + `localStorage`, owns profile, college list and compare tray.
- Create `college-recommender/lib/listAnalysis.ts` — pure tier-balance maths.
- Create `college-recommender/components/AppShell.tsx` — nav, hero, route links.
- Create `college-recommender/components/ProfileForm.tsx` — the card-based form.
- Create `college-recommender/components/MatchResults.tsx` — results list, sort, tier filter, show-more.
- Create `college-recommender/components/CompareTray.tsx` — the pinned tray.
- Create `college-recommender/components/CompareTable.tsx` — the side-by-side table.
- Create `college-recommender/app/{browse,majors,list}/page.tsx` — three routes.
- Create `college-recommender/app/api/classify/route.ts` — proxy.
- Modify `college-recommender/app/page.tsx` — becomes the profile route only.
- Modify `college-recommender/app/layout.tsx` — wraps children in the provider and `AppShell`.
- Modify `college-recommender/components/ActivitiesInput.tsx` — explanation box, recognition display.
- Modify `college-recommender/lib/contract.ts` — mirror v4.0.0.

---

### Task 1: Carry region, setting and type into the catalog

`enrich()` builds a fresh dict and never copies these three, so they are lost even though every one of the 358 tier-1 records has them.

**Files:**
- Modify: `data-pipeline/build_catalog.py`
- Test: `data-pipeline/tests/test_build_catalog.py`

**Interfaces:**
- Consumes: nothing.
- Produces: catalog records with `region: str`, `setting: str`, `type: str`.

- [ ] **Step 1: Write the failing test**

Append to `data-pipeline/tests/test_build_catalog.py`:

```python
class TestPlaceFields:
    """region, setting and type exist on every tier-1 record and were being
    dropped by enrich(), which builds a fresh dict."""

    def test_region_setting_and_type_survive_enrich(self):
        record = enrich(
            {**NON_US, "region": "International", "setting": "urban", "type": "Public"}, None
        )

        assert record["region"] == "International"
        assert record["setting"] == "urban"
        assert record["type"] == "Public"

    def test_they_are_marked_editorial(self):
        record = enrich(
            {**NON_US, "region": "West", "setting": "rural", "type": "Private"}, None
        )

        assert record["provenance"]["region"] == "editorial"
        assert record["provenance"]["setting"] == "editorial"
        assert record["provenance"]["type"] == "editorial"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd data-pipeline && .venv/bin/python -m pytest tests/test_build_catalog.py::TestPlaceFields -q`
Expected: FAIL with `KeyError: 'region'`

- [ ] **Step 3: Write minimal implementation**

In `data-pipeline/build_catalog.py`, inside `enrich()`, add to the provenance dict initialisation:

```python
    provenance = {
        "avg_gpa": "editorial",
        "culture": "editorial",
        "region": "editorial",
        "setting": "editorial",
        "type": "editorial",
    }
```

And add three entries to the returned dict, immediately after `"location": record["location"],`:

```python
        "region": record["region"],
        "setting": record["setting"],
        "type": record["type"],
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd data-pipeline && .venv/bin/python -m pytest -q && .venv/bin/python -m ruff check .`
Expected: all pass, `All checks passed!`

- [ ] **Step 5: Rebuild the catalog and confirm**

Run:
```bash
cd data-pipeline && .venv/bin/python build_catalog.py
.venv/bin/python -c "
import json, collections
c = json.load(open('out/universities.json'))
print('region:', dict(collections.Counter(r['region'] for r in c)))
print('setting:', dict(collections.Counter(r['setting'] for r in c)))
print('type:', dict(collections.Counter(r['type'] for r in c)))"
```
Expected: 358 records split across 5 regions, 3 settings, 2 types — no `None` keys.

- [ ] **Step 6: Commit**

```bash
git add data-pipeline/build_catalog.py data-pipeline/tests/test_build_catalog.py data-pipeline/sources/scorecard_cache.json
git commit -m "feat: carry region, setting and type into the catalog"
```

---

### Task 2: Add student-body composition and official URLs

**Files:**
- Modify: `data-pipeline/build_catalog.py`
- Test: `data-pipeline/tests/test_build_catalog.py`

**Interfaces:**
- Consumes: Task 1's `enrich()`.
- Produces: `population: dict | None` with keys `international_share`, `women_share`, `first_gen_share`; `url: str | None`; `net_price_calculator_url: str | None`; `provenance["population"]`.

- [ ] **Step 1: Write the failing test**

Append to `data-pipeline/tests/test_build_catalog.py`:

```python
POPULATION_ROW = {
    **US_ROW,
    "UGDS_NRA": "0.1172", "UGDS_WOMEN": "0.4823", "FIRST_GEN": "0.2591",
    "INSTURL": "web.mit.edu/", "NPCURL": "https://npc.collegeboard.org/app/mit",
}


class TestPopulation:
    """Composition comes from Scorecard and exists for US schools only."""

    def test_shares_are_extracted(self):
        record = enrich({**NON_US, "country": "USA", "region": "Northeast",
                         "setting": "urban", "type": "Private"}, POPULATION_ROW)

        assert record["population"]["international_share"] == 0.1172
        assert record["population"]["women_share"] == 0.4823
        assert record["population"]["first_gen_share"] == 0.2591
        assert record["provenance"]["population"] == "observed"

    def test_non_us_school_has_no_population(self):
        """Absent, not zeroed - Scorecard covers US institutions only."""
        record = enrich({**NON_US, "region": "International",
                         "setting": "urban", "type": "Public"}, None)

        assert record["population"] is None
        assert record["provenance"]["population"] == "not_applicable"

    def test_partial_composition_keeps_what_exists(self):
        row = {**POPULATION_ROW, "FIRST_GEN": "NA"}
        record = enrich({**NON_US, "country": "USA", "region": "West",
                         "setting": "rural", "type": "Public"}, row)

        assert record["population"]["international_share"] == 0.1172
        assert record["population"]["first_gen_share"] is None

    def test_official_urls_are_carried(self):
        record = enrich({**NON_US, "country": "USA", "region": "Northeast",
                         "setting": "urban", "type": "Private"}, POPULATION_ROW)

        assert record["url"] == "web.mit.edu/"
        assert record["net_price_calculator_url"].endswith("/app/mit")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd data-pipeline && .venv/bin/python -m pytest tests/test_build_catalog.py::TestPopulation -q`
Expected: FAIL with `KeyError: 'population'`

- [ ] **Step 3: Write minimal implementation**

In `data-pipeline/build_catalog.py`, extend `CACHED_COLUMNS` with the five new columns:

```python
CACHED_COLUMNS = (
    "UNITID", "INSTNM", "CITY", "STABBR",
    "ADM_RATE", "SAT_AVG", "UGDS",
    "NPT4_PUB", "NPT4_PRIV", "TUITIONFEE_OUT",
    "C150_4", "MD_EARN_WNE_P10", "MD_EARN_WNE_P6",
    "GRAD_DEBT_MDN", "PCTPELL", "PCTFLOAN",
    # Student-body composition and the school's own links.
    "UGDS_NRA", "UGDS_WOMEN", "FIRST_GEN", "INSTURL", "NPCURL",
)

_POPULATION_COLUMNS = {
    "international_share": "UGDS_NRA",
    "women_share": "UGDS_WOMEN",
    "first_gen_share": "FIRST_GEN",
}


def extract_population(row: dict | None) -> dict | None:
    """Student-body shares, or None when the school has none.

    Scorecard covers US institutions only, so this is absent rather than zero
    for every non-US school.
    """
    if row is None:
        return None
    values = {key: parse_number(row.get(col)) for key, col in _POPULATION_COLUMNS.items()}
    if all(v is None for v in values.values()):
        return None
    return values


def _text_or_none(row: dict | None, column: str) -> str | None:
    value = ((row or {}).get(column) or "").strip()
    return value if value and value not in _MISSING else None
```

Then inside `enrich()`, after the `outcomes` lines, add:

```python
    population = extract_population(row)
    provenance["population"] = (
        "observed" if population else ("absent" if is_us else "not_applicable")
    )
```

And add three entries to the returned dict, after `"outcomes": outcomes,`:

```python
        "population": population,
        "url": _text_or_none(row, "INSTURL"),
        "net_price_calculator_url": _text_or_none(row, "NPCURL"),
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd data-pipeline && .venv/bin/python -m pytest -q && .venv/bin/python -m ruff check .`
Expected: all pass, `All checks passed!`

- [ ] **Step 5: Refresh the cache from the Scorecard CSV**

`sources/scorecard_cache.json` holds only the 16 current `CACHED_COLUMNS` for its 268 matched schools — none of the five new ones — so the cache must be rebuilt from the CSV. The CSV is **not** on disk and must be downloaded. This undated URL was verified live (HTTP 206, `application/zip`); do not add a date suffix, which 404s:

```bash
cd data-pipeline
curl -L --progress-bar -o /tmp/sc.zip \
  https://ed-public-download.scorecard.network/downloads/Most-Recent-Cohorts-Institution.zip
unzip -o -q /tmp/sc.zip -d /tmp
CSV=$(ls /tmp/Most-Recent-Cohorts-Institution*.csv | head -1)
.venv/bin/python build_catalog.py --scorecard "$CSV"
.venv/bin/python -c "
import json
c = json.load(open('out/universities.json'))
us = [r for r in c if r['country'] == 'USA']
print('population present:', len([r for r in c if r['population']]), '/', len(us), 'US')
print('url present:', len([r for r in c if r['url']]))
print('non-US with population:', len([r for r in c if r['country'] != 'USA' and r['population']]))"
```
Expected: population and url present for ~268 US schools; **0** non-US schools with population.

- [ ] **Step 6: Commit**

```bash
git add data-pipeline/build_catalog.py data-pipeline/tests/test_build_catalog.py data-pipeline/sources/scorecard_cache.json
git commit -m "feat: add student-body composition and official URLs to the catalog"
```

---

### Task 3: Contract v4.0.0 — University fields

**Files:**
- Modify: `docs/contracts/score.schema.json`
- Modify: `docs/contracts/recommendation.schema.json`
- Modify: `docs/contracts/profile.schema.json`
- Modify: `services/scoring-service/app/schemas.py`
- Modify: `services/recommendation-service/app/schemas.py`
- Modify: `services/gateway/src/types.ts`
- Test: `services/scoring-service/tests/test_contract_v2.py`

**Interfaces:**
- Consumes: Task 2's catalog fields.
- Produces: `Region`, `Setting`, `InstitutionType`, `Population` types; `University.{region,setting,type,population,url,net_price_calculator_url}`; `CONTRACT_VERSION == "4.0.0"`.

- [ ] **Step 1: Write the failing test**

Append to `services/scoring-service/tests/test_contract_v2.py`:

```python
def test_university_carries_place_and_population():
    uni = University(
        id="mit", name="MIT", country="USA", location="Cambridge, MA",
        region="Northeast", setting="urban", type="Private",
        avg_gpa=3.95, size="small", majors=["Engineering"],
        culture={"collab": 0.7, "quirky": 0.85, "idealist": 0.55,
                 "research": 0.75, "spirit": 0.35, "seminar": 0.55},
        population={"international_share": 0.1028, "women_share": 0.4768,
                    "first_gen_share": 0.2585},
        url="web.mit.edu/",
    )

    assert uni.region == "Northeast"
    assert uni.setting == "urban"
    assert uni.population.international_share == 0.1028
    assert uni.net_price_calculator_url is None


def test_population_may_be_absent():
    uni = University(
        id="ox", name="Oxford", country="UK", location="Oxford",
        region="International", setting="urban", type="Public",
        avg_gpa=3.9, size="medium", majors=["PPE"],
        culture={"collab": 0.5, "quirky": 0.8, "idealist": 0.6,
                 "research": 0.9, "spirit": 0.4, "seminar": 0.9},
    )

    assert uni.population is None
```

And change the version assertion in the same file:

```python
def test_contract_version_is_4():
    """v4.0.0 adds place and population fields and removes preferences.locations."""
    assert CONTRACT_VERSION == "4.0.0"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd services/scoring-service && .venv/bin/python -m pytest tests/test_contract_v2.py -q --no-cov`
Expected: FAIL — `Extra inputs are not permitted [region]` and the version assertion.

- [ ] **Step 3: Write minimal implementation**

In **both** `services/scoring-service/app/schemas.py` and `services/recommendation-service/app/schemas.py`, set the version and add the types:

```python
CONTRACT_VERSION = "4.0.0"

Region = Literal["Northeast", "South", "West", "Midwest", "International"]
Setting = Literal["urban", "suburban", "rural"]
InstitutionType = Literal["Public", "Private"]


class Population(BaseModel):
    """Student-body composition. Absent for non-US schools."""

    model_config = ConfigDict(extra="forbid")

    international_share: float | None = Field(default=None, ge=0, le=1)
    women_share: float | None = Field(default=None, ge=0, le=1)
    first_gen_share: float | None = Field(default=None, ge=0, le=1)
```

In both files, add to `class University`, immediately after `location: str`:

```python
    region: Region
    setting: Setting
    type: InstitutionType
```

and after `culture: Culture`:

```python
    population: Population | None = None
    url: str | None = None
    net_price_calculator_url: str | None = None
```

In `services/gateway/src/types.ts`, set `CONTRACT_VERSION` to `"4.0.0"` and add above `UniversitySummarySchema`:

```ts
export const RegionSchema = z.enum([
  "Northeast",
  "South",
  "West",
  "Midwest",
  "International",
]);
export const SettingSchema = z.enum(["urban", "suburban", "rural"]);
export const InstitutionTypeSchema = z.enum(["Public", "Private"]);

/** Student-body composition. Absent for non-US schools. */
export const PopulationSchema = z
  .object({
    international_share: z.number().min(0).max(1).nullable().optional(),
    women_share: z.number().min(0).max(1).nullable().optional(),
    first_gen_share: z.number().min(0).max(1).nullable().optional(),
  })
  .strict();
```

Then add these five lines to **both** `UniversitySummarySchema` and `UniversitySchema`, after `location`:

```ts
    region: RegionSchema,
    setting: SettingSchema,
    type: InstitutionTypeSchema,
    population: PopulationSchema.nullable().optional(),
    url: z.string().nullable().optional(),
    net_price_calculator_url: z.string().nullable().optional(),
```

In `docs/contracts/score.schema.json`, set `"version": "4.0.0"`, add `"region"`, `"setting"`, `"type"` to `$defs.University.required`, and add to its `properties`:

```json
        "region": { "type": "string", "enum": ["Northeast", "South", "West", "Midwest", "International"] },
        "setting": { "type": "string", "enum": ["urban", "suburban", "rural"] },
        "type": { "type": "string", "enum": ["Public", "Private"] },
        "population": {
          "type": ["object", "null"],
          "additionalProperties": false,
          "description": "Student-body composition. Null for non-US schools; provenance.population reads not_applicable.",
          "properties": {
            "international_share": { "type": ["number", "null"], "minimum": 0, "maximum": 1 },
            "women_share": { "type": ["number", "null"], "minimum": 0, "maximum": 1 },
            "first_gen_share": { "type": ["number", "null"], "minimum": 0, "maximum": 1 }
          }
        },
        "url": { "type": ["string", "null"], "description": "The institution's own site." },
        "net_price_calculator_url": { "type": ["string", "null"], "description": "Where a student finds what they specifically would pay." },
```

Apply the same six properties to `$defs.UniversitySummary` in `docs/contracts/recommendation.schema.json` and set its version to `4.0.0`. Set `docs/contracts/profile.schema.json` to `4.0.0` (its own field changes land in Task 4).

- [ ] **Step 4: Run tests and typecheck to verify they pass**

Run:
```bash
cd services/scoring-service && .venv/bin/python -m pytest -q
cd ../gateway && npm run --silent typecheck
cd ../.. && python3 -c "
import json
for f in ('profile','score','recommendation'):
    d = json.load(open(f'docs/contracts/{f}.schema.json'))
    assert d['version'] == '4.0.0', (f, d['version'])
print('all contracts 4.0.0 and valid JSON')"
```
Expected: tests pass; typecheck reports the recommendation-service fixtures failing — that is Task 4's work, so if `tsc` errors mention only missing `region`/`setting`/`type` in test fixtures, continue.

- [ ] **Step 5: Commit**

```bash
git add docs/contracts services/scoring-service services/recommendation-service services/gateway
git commit -m "feat: contract v4.0.0 adds place and population to University"
```

---

### Task 4: Contract v4.0.0 — Profile preferences and Activity

Removes `locations`, which compared against strings like `"Cambridge, MA"` and so required typing an exact city to fire.

**Files:**
- Modify: `docs/contracts/profile.schema.json`
- Modify: `services/scoring-service/app/schemas.py`
- Modify: `services/recommendation-service/app/schemas.py`
- Modify: `services/gateway/src/types.ts`
- Test: `services/scoring-service/tests/test_new_dimensions.py`

**Interfaces:**
- Consumes: Task 3's `Region`, `Setting`, `InstitutionType`.
- Produces: `Preferences.{regions,settings,institution_type}`; `Activity.description`. `Preferences.locations` no longer exists.

- [ ] **Step 1: Write the failing test**

Append to `services/scoring-service/tests/test_new_dimensions.py`:

```python
class TestPlacePreferences:
    def test_defaults_are_empty_and_unset(self):
        prefs = Profile(gpa=3.8, intended_major="CS").preferences

        assert prefs.regions == []
        assert prefs.settings == []
        assert prefs.institution_type is None

    def test_accepts_regions_and_settings(self):
        prefs = Profile(
            gpa=3.8, intended_major="CS",
            preferences={"regions": ["Northeast", "West"], "settings": ["urban"]},
        ).preferences

        assert prefs.regions == ["Northeast", "West"]
        assert prefs.settings == ["urban"]

    def test_rejects_an_unknown_region(self):
        with pytest.raises(ValidationError):
            Profile(gpa=3.8, intended_major="CS", preferences={"regions": ["Atlantis"]})

    def test_locations_is_gone(self):
        """It compared against 'Cambridge, MA' and could never fire."""
        with pytest.raises(ValidationError):
            Profile(gpa=3.8, intended_major="CS", preferences={"locations": ["CA"]})


class TestActivityDescription:
    def test_description_is_optional(self):
        assert Activity(name="robotics", kind="club").description is None

    def test_description_is_accepted(self):
        activity = Activity(
            name="Science Bowl", kind="competition",
            description="I built an autonomous rover and wrote the vision pipeline",
        )

        assert "rover" in activity.description
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd services/scoring-service && .venv/bin/python -m pytest tests/test_new_dimensions.py -q --no-cov`
Expected: FAIL — `regions` is an extra input, and `locations` is still accepted.

- [ ] **Step 3: Write minimal implementation**

In **both** `app/schemas.py` files, replace the body of `class Preferences`:

```python
class Preferences(BaseModel):
    model_config = ConfigDict(extra="forbid")

    max_tuition: float | None = Field(default=None, ge=0)
    preferred_size: Size | None = None
    scope: Scope = "both"
    # Soft: fold into the `fit` dimension. An empty list means no preference.
    regions: list[Region] = Field(default_factory=list)
    settings: list[Setting] = Field(default_factory=list)
    # Hard: filters candidates before ranking, like scope.
    institution_type: InstitutionType | None = None
```

Note `locations` is deleted, not commented out.

In both files, add to `class Activity` after `kind`:

```python
    description: str | None = Field(default=None, max_length=500)
```

In `services/gateway/src/types.ts`, replace `PreferencesSchema`:

```ts
export const PreferencesSchema = z
  .object({
    max_tuition: z.number().min(0).nullable().optional(),
    preferred_size: z.enum(["small", "medium", "large"]).nullable().optional(),
    scope: z.enum(["usa", "international", "both"]).optional(),
    regions: z.array(RegionSchema).optional(),
    settings: z.array(SettingSchema).optional(),
    institution_type: InstitutionTypeSchema.nullable().optional(),
  })
  .strict();
```

and add to `ActivitySchema`:

```ts
    description: z.string().max(500).nullable().optional(),
```

In `docs/contracts/profile.schema.json`, delete the `"locations"` property from `preferences.properties` and add:

```json
        "regions": { "type": "array", "items": { "type": "string", "enum": ["Northeast", "South", "West", "Midwest", "International"] }, "default": [], "description": "Soft preference folded into the fit dimension. Empty means no preference." },
        "settings": { "type": "array", "items": { "type": "string", "enum": ["urban", "suburban", "rural"] }, "default": [] },
        "institution_type": { "type": ["string", "null"], "enum": ["Public", "Private", null], "description": "Hard filter applied at candidate selection." }
```

and add `"description"` to the activity item properties:

```json
          "description": { "type": ["string", "null"], "maxLength": 500, "description": "Feeds recognition only. Each activity still contributes at most one hit." }
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd services/scoring-service && .venv/bin/python -m pytest -q --no-cov`
Expected: PASS. `test_fit` failures referring to `preferences.locations` are expected and fixed in Task 5.

- [ ] **Step 5: Commit**

```bash
git add docs/contracts services/scoring-service services/recommendation-service services/gateway
git commit -m "feat: contract v4.0.0 swaps preferences.locations for regions, settings and type"
```

---

### Task 5: Score region and setting; filter by institution type

**Files:**
- Modify: `services/scoring-service/app/scoring.py`
- Modify: `services/recommendation-service/app/candidates.py`
- Modify: `services/recommendation-service/app/main.py`
- Test: `services/scoring-service/tests/test_new_dimensions.py`
- Test: `services/recommendation-service/tests/test_scope.py`

**Interfaces:**
- Consumes: Task 4's `Preferences`.
- Produces: `_fit` weighting `0.50 major + 0.25 region + 0.25 setting`; `in_scope(universities, scope, institution_type=None)`.

- [ ] **Step 1: Write the failing tests**

Append to `services/scoring-service/tests/test_new_dimensions.py`:

```python
class TestFitPlaceTerms:
    """Region and setting are soft, folded into `fit` at 0.25 each. An unstated
    preference scores 1.0, not 0.5: the term is a fixed share of the dimension,
    so a neutral value would cost a student an eighth of it for declining to
    answer."""

    def _profile(self, **prefs) -> Profile:
        return Profile(gpa=3.7, intended_major="Computer Science", preferences=prefs)

    def test_no_place_preference_scores_the_same_as_a_full_match(self):
        uni = _uni(region="West", setting="urban")

        assert _fit(self._profile(), uni) == _fit(
            self._profile(regions=["West"], settings=["urban"]), uni
        )

    def test_matching_region_beats_a_mismatch(self):
        matched = _fit(self._profile(regions=["West"]), _uni(region="West"))
        missed = _fit(self._profile(regions=["West"]), _uni(region="South"))

        assert matched > missed

    def test_matching_setting_beats_a_mismatch(self):
        matched = _fit(self._profile(settings=["rural"]), _uni(setting="rural"))
        missed = _fit(self._profile(settings=["rural"]), _uni(setting="urban"))

        assert matched > missed

    def test_any_listed_region_counts(self):
        profile = self._profile(regions=["Northeast", "West"])

        assert _fit(profile, _uni(region="West")) == _fit(profile, _uni(region="Northeast"))

    def test_stays_in_unit_interval(self):
        for region in ("West", "South"):
            for setting in ("urban", "rural"):
                score = _fit(
                    self._profile(regions=["West"], settings=["urban"]),
                    _uni(region=region, setting=setting),
                )
                assert 0.0 <= score <= 1.0
```

Update the `_uni` helper at the top of that file so the new required fields are present:

```python
def _uni(**over) -> University:
    base = dict(
        id="u1", name="U", country="USA", location="CA",
        region="West", setting="urban", type="Private",
        avg_gpa=3.7, size="medium",
        majors=["Computer Science", "Engineering"], culture=NEUTRAL,
    )
    return University(**{**base, **over})
```

and add `_fit` to that file's import from `app.scoring`.

Append to `services/recommendation-service/tests/test_scope.py`:

```python
def test_institution_type_filters_candidates():
    catalog = [_uni("USA"), _uni("UK")]
    catalog[0].type = "Public"
    catalog[1].type = "Private"

    assert [u.type for u in in_scope(catalog, "both", "Public")] == ["Public"]


def test_no_institution_type_keeps_everything():
    catalog = [_uni("USA"), _uni("UK")]

    assert len(in_scope(catalog, "both", None)) == 2


def test_scope_and_type_compose():
    catalog = [_uni("USA"), _uni("UK")]
    catalog[0].type = "Private"
    catalog[1].type = "Private"

    assert [u.country for u in in_scope(catalog, "usa", "Private")] == ["USA"]
```

Update `_uni` in that file to supply the new required fields:

```python
def _uni(country: str) -> University:
    return University(
        id=country.lower(), name=f"U {country}", country=country, location="x",
        region="International" if country != "USA" else "West",
        setting="urban", type="Public",
        avg_gpa=3.5, size="medium", majors=["CS"], culture=NEUTRAL,
    )
```

- [ ] **Step 2: Run tests to verify they fail**

Run:
```bash
cd services/scoring-service && .venv/bin/python -m pytest tests/test_new_dimensions.py::TestFitPlaceTerms -q --no-cov
cd ../recommendation-service && .venv/bin/python -m pytest tests/test_scope.py -q --no-cov
```
Expected: FAIL — `_fit` ignores region and setting; `in_scope()` takes 2 positional arguments.

- [ ] **Step 3: Write minimal implementation**

Replace `_fit` in `services/scoring-service/app/scoring.py`:

```python
def _place_match(preferred: list[str], actual: str) -> float:
    """1.0 when no preference is stated or the school matches one of them.

    Unstated scores 1.0 rather than neutral 0.5 on purpose: unlike the culture
    axes, which drop out of their average when untouched, this term is a fixed
    share of `fit`, so a neutral value would silently cost a student part of the
    dimension for a question they chose not to answer.
    """
    if not preferred:
        return 1.0
    return 1.0 if actual in preferred else 0.0


def _fit(profile: Profile, uni: University) -> float:
    """Major, region and setting. Campus size lives in the personality
    dimension; `location` is display-only and never scored."""
    major = 1.0 if profile.intended_major.lower() in {m.lower() for m in uni.majors} else 0.3
    region = _place_match(profile.preferences.regions, uni.region)
    setting = _place_match(profile.preferences.settings, uni.setting)
    return round(0.50 * major + 0.25 * region + 0.25 * setting, 6)
```

Replace `in_scope` in `services/recommendation-service/app/candidates.py`:

```python
def in_scope(
    universities: list[University],
    scope: str,
    institution_type: str | None = None,
) -> list[University]:
    """Restrict candidates by country scope and institution type.

    Both are hard filters applied before ranking so a requested top_k is still
    filled. An unrecognised scope returns everything rather than nothing.
    """
    if scope == "usa":
        kept = [u for u in universities if u.country == "USA"]
    elif scope == "international":
        kept = [u for u in universities if u.country != "USA"]
    else:
        kept = list(universities)
    if institution_type is not None:
        kept = [u for u in kept if u.type == institution_type]
    return kept
```

In `services/recommendation-service/app/main.py`, update **both** call sites (in `recommend` and `recommend_stream`):

```python
    universities = in_scope(
        load_universities(),
        request.profile.preferences.scope,
        request.profile.preferences.institution_type,
    )
```

- [ ] **Step 4: Run the full gate to verify it passes**

Run:
```bash
cd /Users/treakybanana/Documents/College_Recommendation
PYBIN=.venv/bin/python ./scripts/verify.sh 2>&1 | grep -E "VERIFY|FAILED"
for d in services/scoring-service services/recommendation-service data-pipeline; do
  (cd $d && .venv/bin/python -m ruff check .)
done
```
Expected: `VERIFY: GREEN` and `All checks passed!` three times. Fix any remaining fixture that lacks `region`/`setting`/`type` by adding those three fields.

- [ ] **Step 5: Commit**

```bash
git add services/
git commit -m "feat: score region and setting in fit; filter by institution type"
```

---

### Task 6: Persist the new fields to Postgres

**Files:**
- Modify: `db/schema.sql`
- Modify: `data-pipeline/load.py`
- Modify: `services/recommendation-service/app/candidates.py:41-44`

**Interfaces:**
- Consumes: Task 2's catalog fields.
- Produces: `universities` table columns `region`, `setting`, `type`, `population`, `url`, `net_price_calculator_url`.

- [ ] **Step 1: Add the columns to the schema**

In `db/schema.sql`, inside `CREATE TABLE universities`, add after the `location` line:

```sql
    region          TEXT        NOT NULL,
    setting         TEXT        NOT NULL CHECK (setting IN ('urban','suburban','rural')),
    type            TEXT        NOT NULL CHECK (type IN ('Public','Private')),
```

and after the `culture` line:

```sql
    population      JSONB,                    -- absent for non-US schools
    url             TEXT,
    net_price_calculator_url TEXT,
```

Add an index below the existing ones:

```sql
CREATE INDEX IF NOT EXISTS idx_universities_region ON universities (region);
```

- [ ] **Step 2: Update the loader**

In `data-pipeline/load.py`, add the six columns to the `INSERT` column list, add six `%s` to `VALUES`, add six `EXCLUDED` assignments to the `DO UPDATE SET`, and extend the parameter tuple. The column list becomes:

```
                        id, unitid, name, country, location, region, setting,
                        type, avg_gpa, avg_sat, acceptance_rate, net_price,
                        sticker_tuition, enrollment, size, majors, culture,
                        population, url, net_price_calculator_url, details,
                        provenance
```

with 22 placeholders, and the parameter tuple becomes:

```python
                    (r["id"], r.get("unitid"), r["name"], r["country"], r["location"],
                     r["region"], r["setting"], r["type"],
                     r["avg_gpa"], r.get("avg_sat"), r.get("acceptance_rate"),
                     r.get("net_price"), r.get("sticker_tuition"), r.get("enrollment"),
                     r["size"], Json(r["majors"]), Json(r["culture"]),
                     Json(r["population"]) if r.get("population") else None,
                     r.get("url"), r.get("net_price_calculator_url"),
                     Json(r.get("details")) if r.get("details") else None,
                     Json(r.get("provenance", {}))),
```

Add the six to the `DO UPDATE SET` block:

```sql
                        region = EXCLUDED.region,
                        setting = EXCLUDED.setting,
                        type = EXCLUDED.type,
                        population = EXCLUDED.population,
                        url = EXCLUDED.url,
                        net_price_calculator_url = EXCLUDED.net_price_calculator_url,
```

- [ ] **Step 3: Update the candidate query**

In `services/recommendation-service/app/candidates.py`, replace the `SELECT` in `_load_from_db`:

```python
        rows = conn.execute(
            "SELECT id, unitid, name, country, location, region, setting, type, "
            "avg_gpa, avg_sat, acceptance_rate, net_price, sticker_tuition, "
            "enrollment, size, majors, culture, population, url, "
            "net_price_calculator_url, details, provenance FROM universities"
        ).fetchall()
```

- [ ] **Step 4: Recreate the volume and load**

`db/schema.sql` only runs on first init of an empty volume, so the volume must be dropped.

```bash
cd /Users/treakybanana/Documents/College_Recommendation
open -a Docker; until docker info >/dev/null 2>&1; do sleep 1; done
docker compose down -v && docker compose up -d --build
until curl -fsS localhost:8000/healthz >/dev/null 2>&1; do sleep 1; done
(cd data-pipeline && DATABASE_URL=postgresql://unimatch:unimatch@localhost:5432/unimatch .venv/bin/python load.py)
docker compose exec -T db psql -U unimatch -d unimatch -tc \
  "select count(*), count(region), count(population) from universities;"
```
Expected: `loaded 358 universities`, and counts `358 | 358 | 268`.

- [ ] **Step 5: Run the smoke test**

Run: `./scripts/smoke.sh 2>&1 | tail -2`
Expected: `SMOKE OK: R1_... 5 results`

- [ ] **Step 6: Commit**

```bash
git add db/schema.sql data-pipeline/load.py services/recommendation-service/app/candidates.py
git commit -m "feat: persist place, population and official URLs to Postgres"
```

---

### Task 7: Activity classification endpoint

The table lives in **one place only** — `scoring-service/app/scoring.py`, which
owns it. recommendation-service forwards to scoring-service over the client it
already has, so the spec's promise ("what the student is shown is exactly what
the scorer will do") holds structurally rather than by a test that watches for
drift. Copying the table into a second service was considered and rejected: the
two processes share no import, so nothing could detect divergence.

The forwarding function is injected the same way `rank_fn` already is, because
`recommendation-service/CLAUDE.md` requires unit tests to stay offline.

**Files:**
- Modify: `services/scoring-service/app/scoring.py`
- Modify: `services/scoring-service/app/schemas.py`
- Modify: `services/scoring-service/app/main.py`
- Create: `services/scoring-service/tests/test_classify.py`
- Modify: `services/recommendation-service/app/clients.py`
- Modify: `services/recommendation-service/app/main.py`
- Create: `services/recommendation-service/tests/test_classify_route.py`
- Modify: `services/gateway/src/{types.ts,clients/recs.ts,routes.ts}`
- Create: `services/gateway/test/classify.test.ts`
- Modify: `services/gateway/test/routes.test.ts`, `services/gateway/test/ws.test.ts`

**Interfaces:**
- Consumes: `_ACTIVITY_SUBJECTS` in `scoring-service/app/scoring.py`.
- Produces:
  - `scoring.classify_activity(name, kind="other", description=None) -> list[str]`
  - `POST /classify` on scoring-service, body `{name, kind, description}`, response `{subjects: list[str]}`
  - `clients.make_classify_fn(client=None, url=SCORING_URL) -> Callable[[str, str, str | None], list[str]]`
  - `POST /activities/classify` on recommendation-service, overridable in tests via `app.dependency_overrides[get_classify_fn]`
  - `POST /v1/activities/classify` on the gateway; `RecsClient.classify(body)`

- [ ] **Step 1: Write the failing scoring-service test**

Create `services/scoring-service/tests/test_classify.py`:

```python
"""Classification is exposed from the service that owns the pattern table, so
the UI cannot be shown one answer while the scorer uses another."""
from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import app
from app.scoring import classify_activity

client = TestClient(app)


def _post(**body):
    return client.post("/classify", json=body)


class TestClassifyFunction:
    def test_recognises_a_known_activity(self):
        assert "Computer Science" in classify_activity("FIRST Robotics", "competition")

    def test_returns_empty_for_something_unrecognised(self):
        """An empty list is the signal the UI uses to prompt for an explanation."""
        assert classify_activity("qqzzxx", "other") == []

    def test_matching_is_case_insensitive(self):
        assert classify_activity("ROBOTICS", "club") != []

    def test_the_description_rescues_an_unrecognised_name(self):
        assert classify_activity("Science Bowl", "competition") == []
        assert "Computer Science" in classify_activity(
            "Science Bowl", "competition", "built an autonomous rover and wrote the vision pipeline"
        )

    def test_is_deterministic(self):
        first = classify_activity("Model UN", "club")
        assert first == classify_activity("Model UN", "club")

    def test_agrees_with_what_the_scorer_matches(self):
        """The property that makes one implementation worth the extra hop: a
        school strong in a returned subject must score above neutral."""
        from app.schemas import Activity, Culture, University
        from app.scoring import activity_fit

        subjects = classify_activity("FIRST Robotics", "competition")
        assert subjects
        uni = University(
            id="u1", name="U", country="USA", location="CA",
            region="West", setting="urban", type="Private",
            avg_gpa=3.7, size="medium", majors=list(subjects),
            culture=Culture(collab=0.5, quirky=0.5, idealist=0.5,
                            research=0.5, spirit=0.5, seminar=0.5),
        )

        assert activity_fit([Activity(name="FIRST Robotics", kind="competition")], uni) > 0.5


class TestClassifyEndpoint:
    def test_returns_the_subjects(self):
        response = _post(name="FIRST Robotics", kind="competition")

        assert response.status_code == 200
        assert "Computer Science" in response.json()["subjects"]

    def test_passes_the_description_through(self):
        response = _post(
            name="Science Bowl", kind="competition", description="built an autonomous rover"
        )

        assert response.json()["subjects"] != []

    def test_name_is_required(self):
        assert client.post("/classify", json={"kind": "club"}).status_code == 422

    def test_rejects_an_unknown_kind(self):
        assert _post(name="x", kind="not-a-kind").status_code == 422
```

- [ ] **Step 2: Run it to verify it fails**

Run: `cd services/scoring-service && .venv/bin/python -m pytest tests/test_classify.py -q --no-cov`
Expected: FAIL — `cannot import name 'classify_activity' from 'app.scoring'`

- [ ] **Step 3: Implement classification in scoring-service**

In `services/scoring-service/app/scoring.py`, add directly below the
`_ACTIVITY_SUBJECTS` table:

```python
def classify_activity(name: str, kind: str = "other", description: str | None = None) -> list[str]:
    """Subject families an activity matches.

    Exported so the UI can show a student what was recognised, reading the same
    table `activity_fit` reads. `activity_fit` keeps its own loop because it also
    needs the school-pairing check; this returns the subjects alone.
    """
    text = " ".join(filter(None, (name, kind, description))).lower()
    for pattern, subjects in _ACTIVITY_SUBJECTS:
        if re.search(pattern, text):
            return list(subjects)
    return []
```

In `services/scoring-service/app/schemas.py`, add:

```python
class ClassifyRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1)
    kind: ActivityKind = "other"
    description: str | None = Field(default=None, max_length=500)


class ClassifyResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    subjects: list[str]
```

In `services/scoring-service/app/main.py`, add the route:

```python
from .schemas import ClassifyRequest, ClassifyResponse
from .scoring import classify_activity


@app.post("/classify", response_model=ClassifyResponse)
def classify(request: ClassifyRequest) -> ClassifyResponse:
    """Subject families for one activity. Deterministic, like everything here:
    no clock, no randomness, no network."""
    return ClassifyResponse(
        subjects=classify_activity(request.name, request.kind, request.description)
    )
```

- [ ] **Step 4: Run it to verify it passes**

Run: `cd services/scoring-service && .venv/bin/python -m pytest -q && .venv/bin/python -m ruff check app`
Expected: all pass, `All checks passed!`

- [ ] **Step 5: Write the failing recommendation-service test**

Create `services/recommendation-service/tests/test_classify_route.py`:

```python
"""The route forwards to scoring-service, which owns the pattern table.

The forwarding function is injected, so these tests never open a socket - the
same discipline `rank_fn` follows.
"""
from __future__ import annotations

import httpx
import pytest
from fastapi.testclient import TestClient

from app.clients import make_classify_fn
from app.main import app, get_classify_fn


@pytest.fixture
def client():
    calls: list[tuple[str, str, str | None]] = []

    def fake(name: str, kind: str, description: str | None) -> list[str]:
        calls.append((name, kind, description))
        return ["Computer Science", "Engineering"]

    app.dependency_overrides[get_classify_fn] = lambda: fake
    yield TestClient(app), calls
    app.dependency_overrides.clear()


def test_returns_the_subjects_from_scoring_service(client):
    test_client, _ = client

    response = test_client.post(
        "/activities/classify", json={"name": "FIRST Robotics", "kind": "competition"}
    )

    assert response.status_code == 200
    assert response.json()["subjects"] == ["Computer Science", "Engineering"]


def test_forwards_the_description(client):
    test_client, calls = client

    test_client.post(
        "/activities/classify",
        json={"name": "Science Bowl", "kind": "competition", "description": "built a rover"},
    )

    assert calls == [("Science Bowl", "competition", "built a rover")]


def test_name_is_required(client):
    test_client, _ = client

    assert test_client.post("/activities/classify", json={"kind": "club"}).status_code == 422


def test_an_unreachable_scorer_is_a_502_not_a_crash(client):
    """Recognition is advisory; the UI degrades. It must not surface a 500."""
    test_client, _ = client

    def broken(name: str, kind: str, description: str | None) -> list[str]:
        raise httpx.ConnectError("scoring-service is down")

    app.dependency_overrides[get_classify_fn] = lambda: broken

    response = test_client.post("/activities/classify", json={"name": "robotics", "kind": "club"})

    assert response.status_code == 502


def test_the_client_posts_to_the_scoring_endpoint():
    """Guards the URL and payload shape without a live service."""
    seen: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        seen["body"] = request.read().decode()
        return httpx.Response(200, json={"subjects": ["Music"]})

    transport = httpx.MockTransport(handler)
    with httpx.Client(transport=transport) as http:
        classify = make_classify_fn(client=http, url="http://scoring:8001")
        assert classify("jazz band", "arts", None) == ["Music"]

    assert seen["url"] == "http://scoring:8001/classify"
    assert '"name":"jazz band"' in str(seen["body"]).replace(" ", "")
```

- [ ] **Step 6: Run it to verify it fails**

Run: `cd services/recommendation-service && .venv/bin/python -m pytest tests/test_classify_route.py -q --no-cov`
Expected: FAIL — `cannot import name 'make_classify_fn' from 'app.clients'`

- [ ] **Step 7: Implement the forwarding route**

In `services/recommendation-service/app/clients.py`, add:

```python
def make_classify_fn(
    client: httpx.Client | None = None,
    url: str = SCORING_URL,
) -> Callable[[str, str, str | None], list[str]]:
    """Return classify(name, kind, description) calling scoring-service POST /classify.

    scoring-service owns the pattern table; forwarding keeps one implementation
    rather than a second copy that could silently diverge from the scorer.
    """

    def classify(name: str, kind: str, description: str | None) -> list[str]:
        payload = {"name": name, "kind": kind, "description": description}
        owns = client is None
        c = client or httpx.Client(timeout=10.0)
        try:
            resp = c.post(f"{url}/classify", json=payload)
            resp.raise_for_status()
            data = resp.json()
        finally:
            if owns:
                c.close()
        return list(data["subjects"])

    return classify
```

In `services/recommendation-service/app/schemas.py`, add the same two models as
scoring-service (they mirror one shape across the boundary, exactly as
`University` and `Profile` already do):

```python
class ClassifyRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1)
    kind: ActivityKind = "other"
    description: str | None = Field(default=None, max_length=500)


class ClassifyResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    subjects: list[str]
```

In `services/recommendation-service/app/main.py`, add the dependency and route:

```python
import httpx
from fastapi import Depends

from .clients import make_classify_fn
from .schemas import ClassifyRequest, ClassifyResponse


def get_classify_fn() -> Callable[[str, str, str | None], list[str]]:
    """Injection point: tests override this so no unit test opens a socket."""
    return make_classify_fn()


@app.post("/activities/classify", response_model=ClassifyResponse)
def classify(
    request: ClassifyRequest,
    classify_fn: Callable[[str, str, str | None], list[str]] = Depends(get_classify_fn),
) -> ClassifyResponse:
    """Forward to scoring-service, which owns the pattern table."""
    try:
        subjects = classify_fn(request.name, request.kind, request.description)
    except (httpx.HTTPError, KeyError) as exc:
        raise HTTPException(status_code=502, detail="scoring_service_unavailable") from exc
    return ClassifyResponse(subjects=subjects)
```

adding `from collections.abc import Callable` and, if not already imported,
`HTTPException` to the existing `from fastapi import ...` line.

- [ ] **Step 8: Run it to verify it passes**

Run: `cd services/recommendation-service && .venv/bin/python -m pytest -q && .venv/bin/python -m ruff check app`
Expected: all pass, `All checks passed!`

- [ ] **Step 9: Write the failing gateway test**

Create `services/gateway/test/classify.test.ts`:

```ts
import { afterEach, describe, expect, it } from "vitest";
import type { FastifyInstance } from "fastify";

import { buildServer } from "../src/server.js";
import type { RecsClient, SseFrame } from "../src/clients/recs.js";

function fakeRecs(overrides: Partial<RecsClient> = {}): RecsClient {
  return {
    async recommend() {
      throw new Error("not used");
    },
    async universities() {
      return { universities: [] };
    },
    async classify() {
      return { subjects: ["Computer Science"] };
    },
    // eslint-disable-next-line require-yield
    async *stream(): AsyncGenerator<SseFrame> {
      throw new Error("not used");
    },
    ...overrides,
  } as RecsClient;
}

let app: FastifyInstance;
afterEach(async () => {
  await app?.close();
});

describe("POST /v1/activities/classify", () => {
  it("returns the recognised subjects", async () => {
    app = await buildServer({ recsClient: fakeRecs() });

    const res = await app.inject({
      method: "POST",
      url: "/v1/activities/classify",
      payload: { name: "FIRST Robotics", kind: "competition" },
    });

    expect(res.statusCode).toBe(200);
    expect(res.json().subjects).toContain("Computer Science");
  });

  it("rejects a body with no name", async () => {
    app = await buildServer({ recsClient: fakeRecs() });

    const res = await app.inject({
      method: "POST",
      url: "/v1/activities/classify",
      payload: { kind: "club" },
    });

    expect(res.statusCode).toBe(400);
  });

  it("returns 502 when the upstream fails", async () => {
    app = await buildServer({
      recsClient: fakeRecs({
        async classify() {
          throw new Error("down");
        },
      }),
    });

    const res = await app.inject({
      method: "POST",
      url: "/v1/activities/classify",
      payload: { name: "robotics", kind: "club" },
    });

    expect(res.statusCode).toBe(502);
  });
});
```

Check `services/gateway/src/server.ts` for the exact name of the injected-client
option before writing this — the plan assumes `{ recsClient }`; use whatever the
existing `test/routes.test.ts` passes.

- [ ] **Step 10: Run it to verify it fails**

Run: `cd services/gateway && npx vitest run test/classify.test.ts`
Expected: FAIL — 404, since the route does not exist

- [ ] **Step 11: Implement the gateway route**

In `services/gateway/src/types.ts`:

```ts
export const ClassifyRequestSchema = z
  .object({
    name: z.string().min(1),
    kind: z
      .enum(["competition", "club", "volunteering", "work", "sport", "arts", "research", "other"])
      .default("other"),
    description: z.string().max(500).nullable().optional(),
  })
  .strict();

export const ClassifyResponseSchema = z.object({ subjects: z.array(z.string()) }).strict();

export type ClassifyRequest = z.infer<typeof ClassifyRequestSchema>;
export type ClassifyResponse = z.infer<typeof ClassifyResponseSchema>;
```

In `services/gateway/src/clients/recs.ts`, add to the `RecsClient` interface:

```ts
  classify(body: ClassifyRequest): Promise<ClassifyResponse>;
```

and to the object `createRecsClient` returns:

```ts
    async classify(body: ClassifyRequest): Promise<ClassifyResponse> {
      const res = await fetch(`${baseUrl}/activities/classify`, {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify(body),
      });
      if (!res.ok) {
        throw new Error(`recommendation-service returned ${res.status}`);
      }
      return (await res.json()) as ClassifyResponse;
    },
```

adding `ClassifyRequest` and `ClassifyResponse` to its type import from
`../types.js`.

In `services/gateway/src/routes.ts`, add inside `registerRoutes`, following the
shape of the existing `POST /v1/recommendations` handler:

```ts
  app.post("/v1/activities/classify", async (request, reply) => {
    const parsed = ClassifyRequestSchema.safeParse(request.body);
    if (!parsed.success) {
      return reply.status(400).send({ error: "invalid_request", details: parsed.error.flatten() });
    }
    try {
      return reply.status(200).send(await recs.classify(parsed.data));
    } catch (err) {
      request.log.error(err);
      return reply.status(502).send({ error: "upstream_error" });
    }
  });
```

importing `ClassifyRequestSchema` from `./types.js`.

Add the `classify` stub to every existing fake `RecsClient` in
`test/routes.test.ts` and `test/ws.test.ts`, or `tsc` fails on the widened
interface:

```ts
    async classify() {
      return { subjects: [] };
    },
```

- [ ] **Step 12: Run the full gate to verify it passes**

Run:
```bash
cd /Users/treakybanana/Documents/College_Recommendation
PYBIN=.venv/bin/python ./scripts/verify.sh 2>&1 | grep -E "VERIFY|FAILED"
(cd services/gateway && npx eslint . --ext .ts && echo "eslint clean")
```
Expected: `VERIFY: GREEN`, `eslint clean`

- [ ] **Step 13: Verify the real chain end to end**

The unit tests are all offline, so the forwarding hop itself is only proven
against running services.

```bash
cd /Users/treakybanana/Documents/College_Recommendation
open -a Docker; until docker info >/dev/null 2>&1; do sleep 1; done
docker compose up -d --build
until curl -fsS localhost:8000/healthz >/dev/null 2>&1; do sleep 2; done
curl -fsS -X POST localhost:8001/classify -H 'content-type: application/json' \
  -d '{"name":"FIRST Robotics","kind":"competition"}'
curl -fsS -X POST localhost:8000/v1/activities/classify -H 'content-type: application/json' \
  -d '{"name":"Science Bowl","kind":"competition","description":"built an autonomous rover"}'
```
Expected: both return a `subjects` array containing `Computer Science` — the
second having travelled gateway → recommendation-service → scoring-service.

- [ ] **Step 14: Commit**

```bash
git add services/
git commit -m "feat: add activity classification, owned by scoring-service"
```
### Task 8: Profile store — context plus localStorage

**Files:**
- Create: `college-recommender/lib/profileStore.tsx`
- Create: `college-recommender/lib/profileStore.test.tsx`
- Modify: `college-recommender/lib/contract.ts`

**Interfaces:**
- Consumes: Task 4's contract shape.
- Produces: `ProfileProvider`, and hook `useProfileStore()` returning
  `{ answers, setAnswers, activities, setActivities, form, setForm, list, addToList, removeFromList, isListed, compare, addToCompare, removeFromCompare, COMPARE_LIMIT }`.
  `form` is `{ gpa: string; sat: string; major: string; maxNetPrice: string; scope: Scope; regions: Region[]; settings: Setting[]; institutionType: InstitutionType | null }`.
  `list` and `compare` are `ListedSchool[]`, where
  `ListedSchool = { id: string; name: string; fit: number | null; tier: AdmitTier | null; university: UniversitySummary }`.

- [ ] **Step 1: Write the failing test**

Create `college-recommender/lib/profileStore.test.tsx`:

```tsx
import { act, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it } from "vitest";

import { ProfileProvider, useProfileStore, COMPARE_LIMIT } from "./profileStore";
import type { ListedSchool } from "./profileStore";

const CULTURE = { collab: 0.5, quirky: 0.5, idealist: 0.5, research: 0.5, spirit: 0.5, seminar: 0.5 };

function school(id: string): ListedSchool {
  return {
    id,
    name: `School ${id}`,
    fit: 0.8,
    tier: "target",
    university: {
      country: "USA", location: "CA", region: "West", setting: "urban", type: "Private",
      avg_gpa: 3.7, size: "medium", majors: ["CS"], culture: CULTURE, provenance: {},
    },
  };
}

let store: ReturnType<typeof useProfileStore>;

function Probe() {
  store = useProfileStore();
  return <span>{store.list.length} listed</span>;
}

function mount() {
  return render(
    <ProfileProvider>
      <Probe />
    </ProfileProvider>,
  );
}

beforeEach(() => localStorage.clear());
afterEach(() => localStorage.clear());

describe("profile store", () => {
  it("starts empty", () => {
    mount();
    expect(screen.getByText("0 listed")).toBeTruthy();
  });

  it("adds and removes list entries", () => {
    mount();
    act(() => store.addToList(school("a")));
    expect(store.isListed("a")).toBe(true);
    act(() => store.removeFromList("a"));
    expect(store.isListed("a")).toBe(false);
  });

  it("never lists the same school twice", () => {
    mount();
    act(() => store.addToList(school("a")));
    act(() => store.addToList(school("a")));
    expect(store.list).toHaveLength(1);
  });

  it("caps the compare tray and refuses rather than evicting", () => {
    mount();
    act(() => {
      for (const id of ["a", "b", "c", "d"]) store.addToCompare(school(id));
    });
    expect(store.compare).toHaveLength(COMPARE_LIMIT);
    expect(store.compare.map((s) => s.id)).toEqual(["a", "b", "c"]);
  });

  it("persists the list across a remount", () => {
    mount();
    act(() => store.addToList(school("a")));
    mount();
    expect(store.isListed("a")).toBe(true);
  });

  it("falls back to empty when stored data is corrupt", () => {
    localStorage.setItem("unimatch.v1", "{not json");
    mount();
    expect(store.list).toEqual([]);
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd college-recommender && npx vitest run lib/profileStore.test.tsx`
Expected: FAIL — `Failed to resolve import "./profileStore"`

- [ ] **Step 3: Write minimal implementation**

Create `college-recommender/lib/profileStore.tsx`:

```tsx
"use client";

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";

import type {
  Activity,
  AdmitTier,
  InstitutionType,
  Region,
  Scope,
  Setting,
  UniversitySummary,
} from "./contract";

/** Compare holds finalists, not a spreadsheet; a fourth column stops fitting. */
export const COMPARE_LIMIT = 3;

const STORAGE_KEY = "unimatch.v1";

export interface ListedSchool {
  id: string;
  name: string;
  fit: number | null;
  tier: AdmitTier | null;
  university: UniversitySummary;
}

export interface FormState {
  gpa: string;
  sat: string;
  major: string;
  maxNetPrice: string;
  scope: Scope;
  regions: Region[];
  settings: Setting[];
  institutionType: InstitutionType | null;
}

const EMPTY_FORM: FormState = {
  gpa: "3.8",
  sat: "",
  major: "Computer Science",
  maxNetPrice: "",
  scope: "both",
  regions: [],
  settings: [],
  institutionType: null,
};

interface Persisted {
  form: FormState;
  answers: Record<string, number>;
  activities: Activity[];
  list: ListedSchool[];
}

const EMPTY: Persisted = { form: EMPTY_FORM, answers: {}, activities: [], list: [] };

/** A malformed stored value must not white-screen the app. */
function readStored(): Persisted {
  if (typeof window === "undefined") return EMPTY;
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY);
    if (!raw) return EMPTY;
    const parsed = JSON.parse(raw) as Partial<Persisted>;
    return {
      form: { ...EMPTY_FORM, ...(parsed.form ?? {}) },
      answers: parsed.answers ?? {},
      activities: parsed.activities ?? [],
      list: parsed.list ?? [],
    };
  } catch {
    return EMPTY;
  }
}

interface Store extends Persisted {
  setForm: (next: FormState) => void;
  setAnswers: (next: Record<string, number>) => void;
  setActivities: (next: Activity[]) => void;
  addToList: (school: ListedSchool) => void;
  removeFromList: (id: string) => void;
  isListed: (id: string) => boolean;
  compare: ListedSchool[];
  addToCompare: (school: ListedSchool) => void;
  removeFromCompare: (id: string) => void;
  reset: () => void;
}

const Ctx = createContext<Store | null>(null);

export function ProfileProvider({ children }: { children: ReactNode }) {
  const [state, setState] = useState<Persisted>(EMPTY);
  const [compare, setCompare] = useState<ListedSchool[]>([]);
  const [hydrated, setHydrated] = useState(false);

  // Read once on mount rather than during render: localStorage is unavailable
  // during server rendering, and reading it in the initial state would make
  // the first client render disagree with the server's.
  useEffect(() => {
    setState(readStored());
    setHydrated(true);
  }, []);

  useEffect(() => {
    if (!hydrated) return;
    window.localStorage.setItem(STORAGE_KEY, JSON.stringify(state));
  }, [state, hydrated]);

  const setForm = useCallback((form: FormState) => setState((s) => ({ ...s, form })), []);
  const setAnswers = useCallback(
    (answers: Record<string, number>) => setState((s) => ({ ...s, answers })),
    [],
  );
  const setActivities = useCallback(
    (activities: Activity[]) => setState((s) => ({ ...s, activities })),
    [],
  );
  const addToList = useCallback(
    (school: ListedSchool) =>
      setState((s) =>
        s.list.some((x) => x.id === school.id) ? s : { ...s, list: [...s.list, school] },
      ),
    [],
  );
  const removeFromList = useCallback(
    (id: string) => setState((s) => ({ ...s, list: s.list.filter((x) => x.id !== id) })),
    [],
  );
  const addToCompare = useCallback(
    (school: ListedSchool) =>
      setCompare((current) =>
        current.length >= COMPARE_LIMIT || current.some((x) => x.id === school.id)
          ? current
          : [...current, school],
      ),
    [],
  );
  const removeFromCompare = useCallback(
    (id: string) => setCompare((current) => current.filter((x) => x.id !== id)),
    [],
  );
  const reset = useCallback(() => {
    setState(EMPTY);
    setCompare([]);
  }, []);

  const value = useMemo<Store>(
    () => ({
      ...state,
      setForm,
      setAnswers,
      setActivities,
      addToList,
      removeFromList,
      isListed: (id: string) => state.list.some((x) => x.id === id),
      compare,
      addToCompare,
      removeFromCompare,
      reset,
    }),
    [state, compare, setForm, setAnswers, setActivities, addToList, removeFromList,
     addToCompare, removeFromCompare, reset],
  );

  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

export function useProfileStore(): Store {
  const store = useContext(Ctx);
  if (!store) throw new Error("useProfileStore must be used inside ProfileProvider");
  return store;
}
```

In `college-recommender/lib/contract.ts`, add the mirror types:

```ts
export type Region = "Northeast" | "South" | "West" | "Midwest" | "International";
export type Setting = "urban" | "suburban" | "rural";
export type InstitutionType = "Public" | "Private";

export interface Population {
  international_share?: number | null;
  women_share?: number | null;
  first_gen_share?: number | null;
}
```

and add to `UniversitySummary`:

```ts
  region: Region;
  setting: Setting;
  type: InstitutionType;
  population?: Population | null;
  url?: string | null;
  net_price_calculator_url?: string | null;
```

and to `Profile["preferences"]`, replacing `locations`:

```ts
    regions?: Region[];
    settings?: Setting[];
    institution_type?: InstitutionType | null;
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd college-recommender && npx vitest run && npx tsc --noEmit`
Expected: all pass. Existing fixtures in `ResultCard.test.tsx` and `search.test.ts` need `region`, `setting` and `type` added to their university objects.

- [ ] **Step 5: Commit**

```bash
git add college-recommender/lib
git commit -m "feat: add localStorage-backed profile store"
```

---

### Task 9: Four routes and the app shell

**Files:**
- Create: `college-recommender/components/AppShell.tsx`
- Modify: `college-recommender/app/layout.tsx`
- Create: `college-recommender/app/browse/page.tsx`
- Create: `college-recommender/app/majors/page.tsx`
- Create: `college-recommender/app/list/page.tsx`
- Modify: `college-recommender/app/page.tsx`
- Modify: `college-recommender/app/globals.css`

**Interfaces:**
- Consumes: Task 8's `ProfileProvider`, `useProfileStore`.
- Produces: routes `/`, `/browse`, `/majors`, `/list`; `AppShell` rendering nav, hero and route links; `useCatalog()` hook returning `{ catalog, error }`.

- [ ] **Step 1: Create the catalog hook**

Create `college-recommender/lib/useCatalog.ts`:

```ts
"use client";

import { useEffect, useState } from "react";

import type { University } from "./contract";

/** Fetches the catalog once per mount. Browse and Major Finder both need it. */
export function useCatalog() {
  const [catalog, setCatalog] = useState<University[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    fetch("/api/universities")
      .then(async (res) => {
        if (!res.ok) throw new Error(String(res.status));
        return res.json();
      })
      .then((body) => {
        if (!cancelled) setCatalog(body.universities as University[]);
      })
      .catch(() => {
        if (!cancelled) setError("Couldn't load the catalog. Is the stack running?");
      });
    return () => {
      cancelled = true;
    };
  }, []);

  return { catalog, error };
}
```

- [ ] **Step 2: Create the shell**

Create `college-recommender/components/AppShell.tsx`:

```tsx
"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useState, type ReactNode } from "react";

import { useProfileStore } from "@/lib/profileStore";

const ROUTES: [string, string][] = [
  ["/", "Your profile"],
  ["/browse", "Browse schools"],
  ["/majors", "Major Finder"],
  ["/list", "My college list"],
];

export function AppShell({ children }: { children: ReactNode }) {
  const [theme, setTheme] = useState<"dark" | "light">("dark");
  const pathname = usePathname();
  const { list } = useProfileStore();

  useEffect(() => {
    document.documentElement.setAttribute("data-theme", theme);
  }, [theme]);

  return (
    <>
      <nav className="nav">
        <div className="nav-inner">
          <Link href="/" className="brand">
            <span className="dot" />
            Uni<b>Match</b>
          </Link>
          <div style={{ marginLeft: "auto" }} />
          <button
            className="icon-btn"
            onClick={() => setTheme(theme === "dark" ? "light" : "dark")}
            title="Toggle theme"
            aria-label="Toggle theme"
          >
            {theme === "dark" ? "🌙" : "☀️"}
          </button>
        </div>
      </nav>

      <header className="hero wrap">
        <span className="eyebrow">Holistic matching · not just filters</span>
        <h1>
          Find the university that <span className="g">fits who you are</span>
        </h1>
        <p>
          Put in your real profile, then explore. Compare the schools you like, keep a list of
          where you mean to apply, and see how balanced that list actually is.
        </p>
      </header>

      <div className="wrap">
        <nav className="tabs" aria-label="Sections">
          {ROUTES.map(([href, label]) => (
            <Link
              key={href}
              href={href}
              className={`tab ${pathname === href ? "on" : ""}`}
              aria-current={pathname === href ? "page" : undefined}
            >
              {label}
              {href === "/list" && list.length > 0 && (
                <span className="tab-count">{list.length}</span>
              )}
            </Link>
          ))}
        </nav>
      </div>

      {children}

      <footer>
        UniMatch · figures are approximate and for exploration only — always verify on official
        sites.
        <br />
        Admitted-GPA and campus-culture ratings are editorial estimates; admissions, cost and
        outcome figures come from the U.S. Dept. of Education College Scorecard where available.
      </footer>
    </>
  );
}
```

Append to `college-recommender/app/globals.css`:

```css
.tab {
  text-decoration: none;
  display: inline-flex;
  align-items: center;
  gap: 8px;
}
.tab-count {
  background: var(--accent2);
  color: #0e1116;
  font-size: 11px;
  font-weight: 800;
  min-width: 18px;
  height: 18px;
  border-radius: 9px;
  display: grid;
  place-items: center;
  padding: 0 5px;
}
```

- [ ] **Step 3: Wrap the layout**

Replace the `<body>` contents of `college-recommender/app/layout.tsx` so children are wrapped:

```tsx
import { AppShell } from "@/components/AppShell";
import { ProfileProvider } from "@/lib/profileStore";
```

```tsx
      <body>
        <ProfileProvider>
          <AppShell>{children}</AppShell>
        </ProfileProvider>
      </body>
```

- [ ] **Step 4: Create the three new routes**

Create `college-recommender/app/browse/page.tsx`:

```tsx
"use client";

import { BrowseSection } from "@/components/BrowseSection";
import { useCatalog } from "@/lib/useCatalog";
import { useSchoolModal } from "@/lib/useSchoolModal";

export default function BrowsePage() {
  const { catalog, error } = useCatalog();
  const { open, modal } = useSchoolModal();

  return (
    <main className="wrap">
      <BrowseSection catalog={catalog} error={error} onOpen={open} />
      {modal}
    </main>
  );
}
```

Create `college-recommender/app/majors/page.tsx`:

```tsx
"use client";

import { MajorFinder } from "@/components/MajorFinder";
import { useCatalog } from "@/lib/useCatalog";
import { useSchoolModal } from "@/lib/useSchoolModal";

export default function MajorsPage() {
  const { catalog } = useCatalog();
  const { open, modal } = useSchoolModal();

  return (
    <main className="wrap">
      <MajorFinder catalog={catalog} onOpen={open} />
      {modal}
    </main>
  );
}
```

Create `college-recommender/lib/useSchoolModal.tsx` so all four routes open profiles identically:

```tsx
"use client";

import { useState, type ReactNode } from "react";

import { UniversityModal } from "@/components/UniversityModal";
import type { AdmitTier, UniversitySummary } from "./contract";

interface Opened {
  name: string;
  university: UniversitySummary;
  rationale?: string;
  admitTier?: AdmitTier | null;
}

/** One modal implementation shared by every route. */
export function useSchoolModal(): {
  open: (school: { name: string; university?: UniversitySummary } & Partial<Opened>) => void;
  modal: ReactNode;
} {
  const [opened, setOpened] = useState<Opened | null>(null);

  const open = (school: { name: string; university?: UniversitySummary } & Partial<Opened>) =>
    setOpened({
      name: school.name,
      university: (school.university ?? school) as UniversitySummary,
      rationale: school.rationale,
      admitTier: school.admitTier,
    });

  return {
    open,
    modal: opened ? (
      <UniversityModal
        name={opened.name}
        university={opened.university}
        rationale={opened.rationale}
        admitTier={opened.admitTier}
        onClose={() => setOpened(null)}
      />
    ) : null,
  };
}
```

Create `college-recommender/app/list/page.tsx` as a stub that Task 13 fills:

```tsx
"use client";

export default function ListPage() {
  return (
    <main className="wrap">
      <section className="section">
        <h2>My college list</h2>
        <p className="lead">Coming in the next task.</p>
      </section>
    </main>
  );
}
```

- [ ] **Step 5: Reduce app/page.tsx to the profile route**

Replace the whole of `college-recommender/app/page.tsx` with a shell that Tasks 10 and 11 fill; the nav, hero and footer now live in `AppShell`:

```tsx
"use client";

import { ProfileForm } from "@/components/ProfileForm";

export default function ProfilePage() {
  return (
    <main className="wrap">
      <ProfileForm />
    </main>
  );
}
```

Create a minimal `college-recommender/components/ProfileForm.tsx` so the build passes; Task 10 replaces its body:

```tsx
"use client";

export function ProfileForm() {
  return <div className="panel">Form arrives in Task 10.</div>;
}
```

- [ ] **Step 6: Verify the routes build and render**

Run:
```bash
cd college-recommender
npx tsc --noEmit && npm_config_cache=/tmp/npm-cache npm run build 2>&1 | grep -A6 "Route (app)"
```
Expected: four static routes `/`, `/browse`, `/majors`, `/list` plus the three `/api/*` dynamic routes.

- [ ] **Step 7: Commit**

```bash
git add college-recommender
git commit -m "feat: split the single page into four routes with a shared shell"
```

---

### Task 10: The card-based form

**Files:**
- Modify: `college-recommender/components/ProfileForm.tsx`
- Modify: `college-recommender/components/Questionnaire.tsx`
- Create: `college-recommender/components/PlacePicker.tsx`
- Modify: `college-recommender/app/globals.css`
- Create: `college-recommender/components/ProfileForm.test.tsx`

**Interfaces:**
- Consumes: Task 8's store, Task 9's `ProfileForm` stub.
- Produces: `ProfileForm` submitting to `/api/recommend` and rendering `MatchResults`; `PlacePicker` for region and setting tiles.

- [ ] **Step 1: Write the failing test**

Create `college-recommender/components/ProfileForm.test.tsx`:

```tsx
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import { ProfileProvider } from "@/lib/profileStore";
import { ProfileForm } from "./ProfileForm";

afterEach(cleanup);

function mount() {
  return render(
    <ProfileProvider>
      <ProfileForm />
    </ProfileProvider>,
  );
}

describe("ProfileForm", () => {
  it("offers every region as a toggle", () => {
    mount();

    for (const region of ["Northeast", "South", "West", "Midwest", "International"]) {
      expect(screen.getByRole("button", { name: region })).toBeTruthy();
    }
  });

  it("offers the three campus settings", () => {
    mount();

    for (const setting of ["Urban", "Suburban", "Rural"]) {
      expect(screen.getByRole("button", { name: setting })).toBeTruthy();
    }
  });

  it("offers a public/private choice", () => {
    mount();
    expect(screen.getByLabelText(/public or private/i)).toBeTruthy();
  });

  it("renders no MBTI control", () => {
    mount();
    expect(screen.queryByText(/mbti/i)).toBeNull();
  });

  it("labels both ends of every preference question", () => {
    mount();
    expect(screen.getByText(/I'd rather we all helped each other/i)).toBeTruthy();
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd college-recommender && npx vitest run components/ProfileForm.test.tsx`
Expected: FAIL — the stub renders only placeholder text.

- [ ] **Step 3: Create the place picker**

Create `college-recommender/components/PlacePicker.tsx`:

```tsx
"use client";

/** Toggle tiles for a list-valued preference. Selecting nothing means "no
 *  preference", which the scorer treats as a full match rather than neutral. */
export function PlacePicker<T extends string>({
  legend,
  hint,
  options,
  selected,
  onChange,
}: {
  legend: string;
  hint: string;
  options: readonly { value: T; label: string }[];
  selected: T[];
  onChange: (next: T[]) => void;
}) {
  const toggle = (value: T) =>
    onChange(selected.includes(value) ? selected.filter((v) => v !== value) : [...selected, value]);

  return (
    <fieldset style={{ border: 0, padding: 0, margin: 0 }}>
      <legend className="fld">{legend}</legend>
      <p className="muted" style={{ fontSize: 12.5, margin: "0 0 10px" }}>
        {hint}
      </p>
      <div style={{ display: "flex", flexWrap: "wrap", gap: 8 }}>
        {options.map((option) => (
          <button
            key={option.value}
            type="button"
            className={`chip ${selected.includes(option.value) ? "on" : ""}`}
            aria-pressed={selected.includes(option.value)}
            onClick={() => toggle(option.value)}
          >
            {option.label}
          </button>
        ))}
      </div>
    </fieldset>
  );
}
```

- [ ] **Step 4: Rewrite the questionnaire as labelled halves**

`lib/questionnaire.ts` already carries a `low` and `high` sentence per question — that copy exists and must be used, not rewritten. The five-point `CHOICES` array becomes unused once this lands and nothing else imports it, so delete the `export const CHOICES` line from `lib/questionnaire.ts` in the same step. `foldAnswers` accepts any value in `[0,1]`, so three choices need no change to it.

Replace the returned JSX of `college-recommender/components/Questionnaire.tsx` so each question is a card with two clickable sentences:

```tsx
      {QUESTIONS.map((question) => {
        const value = answers[question.id];
        const choose = (next: number) => {
          const updated = { ...answers };
          if (updated[question.id] === next) delete updated[question.id];
          else updated[question.id] = next;
          onChange(updated);
        };
        return (
          <div key={question.id} className="qcard">
            <p className="qprompt">{question.prompt}</p>
            <div className="qhalves">
              <button
                type="button"
                className={`qhalf ${value !== undefined && value < 0.5 ? "on" : ""}`}
                aria-pressed={value !== undefined && value < 0.5}
                onClick={() => choose(0)}
              >
                {question.low}
              </button>
              <button
                type="button"
                className={`qeither ${value === 0.5 ? "on" : ""}`}
                aria-pressed={value === 0.5}
                onClick={() => choose(0.5)}
              >
                either
              </button>
              <button
                type="button"
                className={`qhalf ${value !== undefined && value > 0.5 ? "on" : ""}`}
                aria-pressed={value !== undefined && value > 0.5}
                onClick={() => choose(1)}
              >
                {question.high}
              </button>
            </div>
          </div>
        );
      })}
```

Append to `college-recommender/app/globals.css`:

```css
/* ---------- question cards ---------- */
.qcard {
  background: var(--panel2);
  border: 1px solid var(--line);
  border-radius: var(--r-sm);
  padding: 16px 18px;
  margin-bottom: 12px;
}
.qprompt {
  margin: 0 0 12px;
  font-size: 15px;
  font-weight: 650;
}
.qhalves {
  display: grid;
  grid-template-columns: 1fr auto 1fr;
  gap: 8px;
  align-items: stretch;
}
.qhalf,
.qeither {
  background: var(--panel);
  border: 1px solid var(--line);
  border-radius: var(--r-sm);
  color: var(--muted);
  font: inherit;
  font-size: 13.5px;
  padding: 12px 14px;
  cursor: pointer;
  transition: 0.15s;
  text-align: left;
}
.qeither {
  text-align: center;
  color: var(--faint);
  font-size: 12px;
  padding: 12px 10px;
}
.qhalf:hover,
.qeither:hover {
  border-color: var(--accent);
  color: var(--ink);
}
.qhalf.on,
.qeither.on {
  border-color: var(--accent);
  color: var(--ink);
  background: color-mix(in srgb, var(--accent) 14%, transparent);
}
@media (max-width: 620px) {
  .qhalves {
    grid-template-columns: 1fr;
  }
}
```

- [ ] **Step 5: Write the form**

Replace `college-recommender/components/ProfileForm.tsx` entirely:

```tsx
"use client";

import { useState } from "react";

import { ActivitiesInput } from "@/components/ActivitiesInput";
import { MatchResults } from "@/components/MatchResults";
import { PlacePicker } from "@/components/PlacePicker";
import { Questionnaire } from "@/components/Questionnaire";
import type { InstitutionType, RecommendationResponse, Region, Scope, Setting } from "@/lib/contract";
import { useProfileStore } from "@/lib/profileStore";
import { foldAnswers } from "@/lib/questionnaire";
import { MAJORS } from "@/lib/majors";

const REGIONS: readonly { value: Region; label: string }[] = [
  { value: "Northeast", label: "Northeast" },
  { value: "South", label: "South" },
  { value: "West", label: "West" },
  { value: "Midwest", label: "Midwest" },
  { value: "International", label: "International" },
];

const SETTINGS: readonly { value: Setting; label: string }[] = [
  { value: "urban", label: "Urban" },
  { value: "suburban", label: "Suburban" },
  { value: "rural", label: "Rural" },
];

type Status =
  | { kind: "idle" }
  | { kind: "loading" }
  | { kind: "ok"; response: RecommendationResponse }
  | { kind: "error"; message: string };

export function ProfileForm() {
  const { form, setForm, answers, setAnswers, activities, setActivities, reset } =
    useProfileStore();
  const [status, setStatus] = useState<Status>({ kind: "idle" });

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    setStatus({ kind: "loading" });
    const { culturePrefs, personality } = foldAnswers(answers);

    const body = {
      profile: {
        gpa: Number(form.gpa),
        ...(form.sat ? { sat: Number(form.sat) } : {}),
        intended_major: form.major,
        culture_prefs: culturePrefs,
        personality,
        activities,
        preferences: {
          scope: form.scope,
          regions: form.regions,
          settings: form.settings,
          institution_type: form.institutionType,
          ...(form.maxNetPrice ? { max_tuition: Number(form.maxNetPrice) } : {}),
        },
      },
      top_k: 50,
    };

    try {
      const res = await fetch("/api/recommend", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify(body),
      });
      const payload = await res.json();
      if (!res.ok) {
        setStatus({
          kind: "error",
          message:
            res.status === 503
              ? "Can't reach the recommendation service. Is the stack running?"
              : res.status === 400
                ? "That profile didn't validate — check the GPA and SAT ranges."
                : `The recommendation service failed (${payload?.status ?? res.status}).`,
        });
        return;
      }
      setStatus({ kind: "ok", response: payload as RecommendationResponse });
    } catch {
      setStatus({ kind: "error", message: "Network error. Is the app still running?" });
    }
  }

  return (
    <>
      <form onSubmit={submit} className="panel" style={{ marginTop: 8 }}>
        <h2>Where you stand</h2>
        <div className="grid3" style={{ marginTop: 14 }}>
          <div>
            <label className="fld" htmlFor="gpa">
              Your GPA (4.0 scale)
            </label>
            <input
              id="gpa" type="number" required min={0} max={4} step={0.01}
              value={form.gpa} onChange={(e) => setForm({ ...form, gpa: e.target.value })}
            />
          </div>
          <div>
            <label className="fld" htmlFor="sat">
              SAT <span style={{ color: "var(--faint)" }}>(optional)</span>
            </label>
            <input
              id="sat" type="number" min={400} max={1600} step={10} placeholder="e.g. 1400"
              value={form.sat} onChange={(e) => setForm({ ...form, sat: e.target.value })}
            />
          </div>
          <div>
            <label className="fld" htmlFor="budget">
              Max net price / yr <span style={{ color: "var(--faint)" }}>(after aid)</span>
            </label>
            <input
              id="budget" type="number" min={0} step={1000} placeholder="no limit"
              value={form.maxNetPrice}
              onChange={(e) => setForm({ ...form, maxNetPrice: e.target.value })}
            />
          </div>
        </div>

        <div className="grid2" style={{ marginTop: 18 }}>
          <div>
            <label className="fld" htmlFor="major">
              Intended major / field
            </label>
            <select
              id="major" value={form.major}
              onChange={(e) => setForm({ ...form, major: e.target.value })}
            >
              {MAJORS.map((m) => (
                <option key={m} value={m}>{m}</option>
              ))}
            </select>
          </div>
          <div>
            <label className="fld" htmlFor="instType">
              Public or private
            </label>
            <select
              id="instType" value={form.institutionType ?? ""}
              onChange={(e) =>
                setForm({
                  ...form,
                  institutionType: (e.target.value || null) as InstitutionType | null,
                })
              }
            >
              <option value="">Either</option>
              <option value="Public">Public only</option>
              <option value="Private">Private only</option>
            </select>
          </div>
        </div>

        <h2 style={{ marginTop: 30 }}>Where you want to be</h2>
        <div style={{ marginTop: 14 }}>
          <PlacePicker
            legend="Region"
            hint="A preference, not a filter — a great fit elsewhere still appears."
            options={REGIONS}
            selected={form.regions}
            onChange={(regions) => setForm({ ...form, regions })}
          />
        </div>
        <div style={{ marginTop: 20 }}>
          <PlacePicker
            legend="Campus setting"
            hint="Also a preference. Only 28 of 358 schools are rural, so this nudges rather than excludes."
            options={SETTINGS}
            selected={form.settings}
            onChange={(settings) => setForm({ ...form, settings })}
          />
        </div>
        <div style={{ marginTop: 20, maxWidth: 360 }}>
          <label className="fld" htmlFor="scope">
            Country
          </label>
          <select
            id="scope" value={form.scope}
            onChange={(e) => setForm({ ...form, scope: e.target.value as Scope })}
          >
            <option value="both">Anywhere — US and international</option>
            <option value="usa">United States only</option>
            <option value="international">Outside the US only</option>
          </select>
        </div>

        <h2 style={{ marginTop: 30 }}>About you</h2>
        <Questionnaire answers={answers} onChange={setAnswers} />

        <h2 style={{ marginTop: 30 }}>What you do</h2>
        <ActivitiesInput activities={activities} onChange={setActivities} />

        <div style={{ display: "flex", gap: 10, marginTop: 24 }}>
          <button className="btn" type="submit" disabled={status.kind === "loading"}>
            {status.kind === "loading" ? "Matching…" : "✨ Show my matches"}
          </button>
          <button
            type="button" className="btn ghost"
            onClick={() => {
              reset();
              setStatus({ kind: "idle" });
            }}
          >
            Start over
          </button>
        </div>
      </form>

      {status.kind === "error" && (
        <p role="alert" className="notice error" style={{ marginTop: 22 }}>
          {status.message}
        </p>
      )}

      {status.kind === "ok" && <MatchResults response={status.response} />}
    </>
  );
}
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `cd college-recommender && npx vitest run && npx tsc --noEmit && npx eslint app lib components`
Expected: all pass, no lint output. `MatchResults` does not exist yet — create it as a stub returning `null` if the build blocks, and Task 12 fills it.

- [ ] **Step 7: Commit**

```bash
git add college-recommender
git commit -m "feat: rebuild the form as labelled cards with region and setting pickers"
```

---

### Task 11: Activity recognition and the explanation box

**Files:**
- Create: `college-recommender/app/api/classify/route.ts`
- Modify: `college-recommender/components/ActivitiesInput.tsx`
- Create: `college-recommender/components/ActivitiesInput.test.tsx`
- Modify: `college-recommender/lib/contract.ts`

**Interfaces:**
- Consumes: Task 7's `POST /v1/activities/classify`.
- Produces: `Activity.description`; `POST /api/classify` proxy.

- [ ] **Step 1: Write the failing test**

Create `college-recommender/components/ActivitiesInput.test.tsx`:

```tsx
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { ActivitiesInput } from "./ActivitiesInput";
import type { Activity } from "@/lib/contract";

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

const LISTED: Activity[] = [
  { name: "FIRST Robotics", kind: "competition", subjects: ["Engineering"] },
  { name: "Science Bowl", kind: "competition", subjects: [] },
];

describe("ActivitiesInput", () => {
  it("shows what was recognised", () => {
    render(<ActivitiesInput activities={LISTED} onChange={() => {}} />);

    expect(screen.getByText(/recognised as/i).textContent).toContain("Engineering");
  });

  it("says so when nothing was recognised, rather than failing silently", () => {
    render(<ActivitiesInput activities={LISTED} onChange={() => {}} />);

    expect(screen.getByText(/not recognised/i)).toBeTruthy();
  });

  it("offers an explanation field for an unrecognised activity", () => {
    render(<ActivitiesInput activities={LISTED} onChange={() => {}} />);

    expect(screen.getByLabelText(/explain Science Bowl/i)).toBeTruthy();
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd college-recommender && npx vitest run components/ActivitiesInput.test.tsx`
Expected: FAIL — no "recognised as" text, and `subjects` is not on `Activity`.

- [ ] **Step 3: Add the proxy and the client type**

Create `college-recommender/app/api/classify/route.ts`:

```ts
/** Server-side proxy, same reasoning as /api/recommend: GATEWAY_URL stays
 *  server-side and the gateway needs no CORS. */
const GATEWAY_URL = process.env.GATEWAY_URL ?? "http://localhost:8000";

export async function POST(request: Request) {
  let body: unknown;
  try {
    body = await request.json();
  } catch {
    return Response.json({ error: "invalid_json" }, { status: 400 });
  }
  try {
    const upstream = await fetch(`${GATEWAY_URL}/v1/activities/classify`, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify(body),
    });
    if (!upstream.ok) {
      return Response.json({ error: "upstream_error" }, { status: 502 });
    }
    return Response.json(await upstream.json());
  } catch {
    return Response.json({ error: "gateway_unreachable" }, { status: 503 });
  }
}
```

In `college-recommender/lib/contract.ts`, extend `Activity`:

```ts
export interface Activity {
  name: string;
  kind: ActivityKind;
  years?: number | null;
  description?: string | null;
  /** Client-side only: what the classify endpoint recognised. Not sent back. */
  subjects?: string[];
}
```

- [ ] **Step 4: Rewrite the activities input**

Replace `college-recommender/components/ActivitiesInput.tsx` entirely:

```tsx
"use client";

import { useState } from "react";

import type { Activity, ActivityKind } from "@/lib/contract";

const KINDS: ActivityKind[] = [
  "competition", "club", "research", "volunteering", "sport", "arts", "work", "other",
];

/** Ask the server what an activity matches. The endpoint shares one table with
 *  the scorer, so what we show is exactly what will be scored. */
async function classify(activity: Activity): Promise<string[]> {
  try {
    const res = await fetch("/api/classify", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({
        name: activity.name,
        kind: activity.kind,
        description: activity.description ?? null,
      }),
    });
    if (!res.ok) return [];
    return (await res.json()).subjects as string[];
  } catch {
    // Recognition is advisory. Failing to reach it must never block entry.
    return [];
  }
}

export function ActivitiesInput({
  activities,
  onChange,
}: {
  activities: Activity[];
  onChange: (next: Activity[]) => void;
}) {
  const [name, setName] = useState("");
  const [kind, setKind] = useState<ActivityKind>("competition");

  const add = async () => {
    const trimmed = name.trim();
    if (!trimmed) return;
    const activity: Activity = { name: trimmed, kind };
    const next = [...activities, { ...activity, subjects: await classify(activity) }];
    onChange(next);
    setName("");
  };

  const explain = async (index: number, description: string) => {
    const updated = { ...activities[index], description };
    const next = [...activities];
    next[index] = { ...updated, subjects: await classify(updated) };
    onChange(next);
  };

  return (
    <div>
      <p className="lead" style={{ fontSize: 14 }}>
        Competitions, clubs, research, jobs — whatever you actually spend time on. We&rsquo;ll
        tell you what we recognised, and you can explain anything we miss.
      </p>

      <div style={{ display: "flex", gap: 10, alignItems: "flex-end", flexWrap: "wrap" }}>
        <div style={{ flex: "2 1 240px" }}>
          <label className="fld" htmlFor="act-name">
            What you did
          </label>
          <input
            id="act-name" type="text" value={name}
            placeholder="e.g. FIRST Robotics, Model UN, hospital volunteering"
            onChange={(e) => setName(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter") {
                e.preventDefault();
                void add();
              }
            }}
          />
        </div>
        <div style={{ flex: "1 1 140px" }}>
          <label className="fld" htmlFor="act-kind">
            Kind
          </label>
          <select
            id="act-kind" value={kind}
            onChange={(e) => setKind(e.target.value as ActivityKind)}
          >
            {KINDS.map((k) => (
              <option key={k} value={k}>{k[0].toUpperCase() + k.slice(1)}</option>
            ))}
          </select>
        </div>
        <button type="button" className="btn ghost" onClick={() => void add()}>
          Add
        </button>
      </div>

      {activities.length > 0 && (
        <div style={{ marginTop: 16, display: "grid", gap: 12 }}>
          {activities.map((activity, index) => {
            const recognised = (activity.subjects ?? []).length > 0;
            return (
              <div key={`${activity.name}-${index}`} className="qcard">
                <div className="card-head">
                  <div>
                    <b style={{ fontSize: 14.5 }}>{activity.name}</b>
                    <span className="muted" style={{ fontSize: 12.5 }}> · {activity.kind}</span>
                  </div>
                  <button
                    type="button" className="chip"
                    onClick={() => onChange(activities.filter((_, i) => i !== index))}
                  >
                    Remove
                  </button>
                </div>

                {recognised ? (
                  <p style={{ margin: "8px 0 0", fontSize: 13, color: "var(--good)" }}>
                    recognised as: {(activity.subjects ?? []).join(", ")}
                  </p>
                ) : (
                  <p style={{ margin: "8px 0 0", fontSize: 13, color: "var(--warn)" }}>
                    not recognised — tell us what you did and we&rsquo;ll try again
                  </p>
                )}

                <label
                  className="fld"
                  htmlFor={`explain-${index}`}
                  style={{ marginTop: 10 }}
                >
                  Explain {activity.name} <span style={{ color: "var(--faint)" }}>(optional)</span>
                </label>
                <input
                  id={`explain-${index}`}
                  type="text"
                  maxLength={500}
                  defaultValue={activity.description ?? ""}
                  placeholder="e.g. I built an autonomous rover and wrote the vision pipeline"
                  onBlur={(e) => void explain(index, e.target.value)}
                />
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
```

- [ ] **Step 5: Strip client-only fields before submitting**

In `college-recommender/components/ProfileForm.tsx`, replace `activities,` inside the request body with a mapped form, so `subjects` is never sent to a `strict` schema:

```tsx
        activities: activities.map(({ name, kind, years, description }) => ({
          name,
          kind,
          ...(years == null ? {} : { years }),
          ...(description ? { description } : {}),
        })),
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `cd college-recommender && npx vitest run && npx tsc --noEmit && npx eslint app lib components`
Expected: all pass.

- [ ] **Step 7: Commit**

```bash
git add college-recommender
git commit -m "feat: show recognised activity subjects and add an explanation box"
```

---

### Task 12: Match results, compare tray and compare table

**Files:**
- Create: `college-recommender/components/MatchResults.tsx`
- Create: `college-recommender/components/CompareTray.tsx`
- Create: `college-recommender/components/CompareTable.tsx`
- Create: `college-recommender/components/CompareTable.test.tsx`
- Modify: `college-recommender/components/ResultCard.tsx`
- Modify: `college-recommender/components/AppShell.tsx`
- Modify: `college-recommender/app/globals.css`

**Interfaces:**
- Consumes: Task 8's store (`compare`, `addToCompare`, `COMPARE_LIMIT`, `addToList`, `isListed`).
- Produces: `MatchResults({ response })`; `CompareTray`; `CompareTable({ schools })`.

- [ ] **Step 1: Write the failing test**

Create `college-recommender/components/CompareTable.test.tsx`:

```tsx
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import { CompareTable } from "./CompareTable";
import type { ListedSchool } from "@/lib/profileStore";

afterEach(cleanup);

const CULTURE = { collab: 0.5, quirky: 0.5, idealist: 0.5, research: 0.5, spirit: 0.5, seminar: 0.5 };

function school(id: string, over: Partial<ListedSchool["university"]> = {}): ListedSchool {
  return {
    id,
    name: `School ${id}`,
    fit: 0.79,
    tier: "reach",
    university: {
      country: "USA", location: "CA", region: "West", setting: "urban", type: "Private",
      avg_gpa: 3.95, avg_sat: 1560, acceptance_rate: 0.046, net_price: 20111,
      enrollment: 4600, size: "small", majors: ["Engineering"], culture: CULTURE,
      provenance: { avg_sat: "observed", acceptance_rate: "observed" },
      ...over,
    },
  };
}

describe("CompareTable", () => {
  it("renders one column per school", () => {
    render(<CompareTable schools={[school("a"), school("b")]} />);

    expect(screen.getByText("School a")).toBeTruthy();
    expect(screen.getByText("School b")).toBeTruthy();
  });

  it("shows the fit percentage", () => {
    render(<CompareTable schools={[school("a")]} />);

    expect(screen.getByText("79%")).toBeTruthy();
  });

  it("renders a not_applicable stat as n/a, never zero", () => {
    render(
      <CompareTable
        schools={[school("a", { avg_sat: null, provenance: { avg_sat: "not_applicable" } })]}
      />,
    );

    expect(screen.getByText("n/a")).toBeTruthy();
    expect(screen.queryByText("0")).toBeNull();
  });

  it("renders an absent stat as an em dash", () => {
    render(
      <CompareTable
        schools={[
          school("a", { acceptance_rate: null, provenance: { acceptance_rate: "absent" } }),
        ]}
      />,
    );

    expect(screen.getByText("—")).toBeTruthy();
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd college-recommender && npx vitest run components/CompareTable.test.tsx`
Expected: FAIL — `Failed to resolve import "./CompareTable"`

- [ ] **Step 3: Write the compare table**

Create `college-recommender/components/CompareTable.tsx`:

```tsx
import { AXIS_LABELS, CULTURE_AXES } from "@/lib/contract";
import { formatStat, tierLabel, type StatKind } from "@/lib/format";
import type { ListedSchool } from "@/lib/profileStore";

const ROWS: { label: string; key: string; kind: StatKind }[] = [
  { label: "Avg GPA", key: "avg_gpa", kind: "decimal" },
  { label: "Avg SAT", key: "avg_sat", kind: "score" },
  { label: "Acceptance", key: "acceptance_rate", kind: "percent" },
  { label: "Net price", key: "net_price", kind: "money" },
  { label: "Undergrads", key: "enrollment", kind: "number" },
];

export function CompareTable({ schools }: { schools: ListedSchool[] }) {
  if (schools.length === 0) return null;

  return (
    <div style={{ overflowX: "auto" }}>
      <table className="cmp">
        <thead>
          <tr>
            <th />
            {schools.map((s) => (
              <th key={s.id}>
                {s.name}
                <div className="loc">
                  {s.university.location} · {s.university.country}
                </div>
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          <tr>
            <th>Fit</th>
            {schools.map((s) => (
              <td key={s.id}>
                <b>{s.fit === null ? "—" : `${Math.round(s.fit * 100)}%`}</b>
              </td>
            ))}
          </tr>
          <tr>
            <th>Tier</th>
            {schools.map((s) => (
              <td key={s.id}>
                {tierLabel(s.tier) ? (
                  <span className={`tier ${s.tier}`}>{tierLabel(s.tier)}</span>
                ) : (
                  "—"
                )}
              </td>
            ))}
          </tr>

          {ROWS.map((row) => (
            <tr key={row.key}>
              <th>{row.label}</th>
              {schools.map((s) => {
                const uni = s.university as unknown as Record<string, number | null | undefined>;
                const rendered = formatStat(
                  uni[row.key],
                  s.university.provenance[row.key],
                  row.kind,
                );
                return (
                  <td key={s.id} title={rendered.note ?? undefined}>
                    {rendered.text}
                    {rendered.note && <span className="note"> {rendered.note}</span>}
                  </td>
                );
              })}
            </tr>
          ))}

          <tr>
            <th>Setting</th>
            {schools.map((s) => (
              <td key={s.id}>
                {s.university.setting} · {s.university.type}
              </td>
            ))}
          </tr>

          {CULTURE_AXES.map((axis) => (
            <tr key={axis}>
              <th style={{ fontWeight: 500, fontSize: 12 }}>{AXIS_LABELS[axis].right}</th>
              {schools.map((s) => (
                <td key={s.id}>
                  <div className="fit-bar" style={{ maxWidth: 120 }}>
                    <span style={{ width: `${s.university.culture[axis] * 100}%` }} />
                  </div>
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
```

Append to `college-recommender/app/globals.css`:

```css
/* ---------- compare ---------- */
.cmp {
  width: 100%;
  border-collapse: collapse;
  font-size: 14px;
}
.cmp th,
.cmp td {
  border-bottom: 1px solid var(--line);
  padding: 10px 14px;
  text-align: left;
  vertical-align: middle;
}
.cmp thead th {
  font-size: 15px;
  font-weight: 750;
  vertical-align: bottom;
}
.cmp tbody th {
  color: var(--muted);
  font-size: 12.5px;
  font-weight: 650;
  white-space: nowrap;
}
.tray {
  position: fixed;
  left: 50%;
  transform: translateX(-50%);
  bottom: 18px;
  z-index: 50;
  display: flex;
  gap: 10px;
  align-items: center;
  background: var(--panel);
  border: 1px solid var(--line);
  border-radius: 999px;
  padding: 10px 14px;
  box-shadow: var(--shadow);
}
```

- [ ] **Step 4: Write the tray and the results list**

Create `college-recommender/components/CompareTray.tsx`:

```tsx
"use client";

import { useState } from "react";

import { CompareTable } from "@/components/CompareTable";
import { COMPARE_LIMIT, useProfileStore } from "@/lib/profileStore";

export function CompareTray() {
  const { compare, removeFromCompare } = useProfileStore();
  const [open, setOpen] = useState(false);

  if (compare.length === 0) return null;

  return (
    <>
      <div className="tray">
        <span className="muted" style={{ fontSize: 13 }}>
          Comparing {compare.length}/{COMPARE_LIMIT}
        </span>
        {compare.map((s) => (
          <button key={s.id} type="button" className="chip on" onClick={() => removeFromCompare(s.id)}>
            {s.name} ✕
          </button>
        ))}
        <button type="button" className="btn sm" onClick={() => setOpen(true)}>
          Compare
        </button>
      </div>

      {open && (
        <div className="modal-back" role="dialog" aria-modal="true" aria-label="Compare schools"
             onClick={() => setOpen(false)}>
          <div className="modal" style={{ maxWidth: 980 }} onClick={(e) => e.stopPropagation()}>
            <div className="card-head">
              <h2 style={{ marginBottom: 2 }}>Side by side</h2>
              <button className="icon-btn" onClick={() => setOpen(false)} aria-label="Close">✕</button>
            </div>
            <CompareTable schools={compare} />
          </div>
        </div>
      )}
    </>
  );
}
```

Create `college-recommender/components/MatchResults.tsx`:

```tsx
"use client";

import { useState } from "react";

import { ResultCard } from "@/components/ResultCard";
import type { RecommendationResponse, Result } from "@/lib/contract";
import { useProfileStore } from "@/lib/profileStore";
import { useSchoolModal } from "@/lib/useSchoolModal";

const PAGE = 10;
type Sort = "match" | "price" | "selectivity";

const SORTS: [Sort, string][] = [
  ["match", "Best match"],
  ["price", "Lowest price"],
  ["selectivity", "Most selective"],
];

export function MatchResults({ response }: { response: RecommendationResponse }) {
  const [sort, setSort] = useState<Sort>("match");
  const [tiers, setTiers] = useState<string[]>([]);
  const [shown, setShown] = useState(PAGE);
  const { open, modal } = useSchoolModal();

  const all = response.results;
  const filtered = tiers.length
    ? all.filter((r) => r.admit_tier && tiers.includes(r.admit_tier))
    : all;
  const results = [...filtered].sort((a, b) => {
    if (sort === "price") return (a.university.net_price ?? 1e9) - (b.university.net_price ?? 1e9);
    if (sort === "selectivity")
      return (a.university.acceptance_rate ?? 1) - (b.university.acceptance_rate ?? 1);
    return b.score - a.score;
  });

  const toggleTier = (tier: string) => {
    setTiers((current) =>
      current.includes(tier) ? current.filter((t) => t !== tier) : [...current, tier],
    );
    setShown(PAGE);
  };

  if (all.length === 0) {
    return (
      <p className="notice empty" style={{ marginTop: 22 }}>
        No schools matched. Try raising your maximum net price, widening the country or
        institution-type filter, or choosing a different major.
      </p>
    );
  }

  return (
    <section className="section" id="results">
      <h2>Your matches</h2>
      <p className="muted" style={{ fontSize: 14, margin: "0 0 18px" }}>
        Showing {Math.min(shown, results.length)} of {results.length}
        {tiers.length > 0 && <> (filtered from {all.length})</>} · click a school for its full
        profile
      </p>

      <div style={{ display: "flex", gap: 8, flexWrap: "wrap", alignItems: "center", marginBottom: 18 }}>
        <span className="muted" style={{ fontSize: 13 }}>Sort</span>
        {SORTS.map(([key, label]) => (
          <button
            key={key} type="button" className={`chip ${sort === key ? "on" : ""}`}
            onClick={() => setSort(key)}
          >
            {label}
          </button>
        ))}
        <span className="muted" style={{ fontSize: 13, marginLeft: 10 }}>Filter</span>
        {["reach", "target", "safety"].map((tier) => (
          <button
            key={tier} type="button" className={`chip ${tiers.includes(tier) ? "on" : ""}`}
            onClick={() => toggleTier(tier)}
          >
            {tier[0].toUpperCase() + tier.slice(1)}
          </button>
        ))}
      </div>

      <div className="cards">
        {results.slice(0, shown).map((result: Result, index) => (
          <ResultCard key={result.university_id} result={result} rank={index + 1} onOpen={open} />
        ))}
      </div>

      {results.length > shown && (
        <div style={{ textAlign: "center", marginTop: 20 }}>
          <button type="button" className="btn ghost" onClick={() => setShown(shown + PAGE)}>
            Show more schools ({results.length - shown} left)
          </button>
        </div>
      )}

      {modal}
    </section>
  );
}
```

- [ ] **Step 5: Add list and compare controls to the result card**

In `college-recommender/components/ResultCard.tsx`, import the store and replace the "View full profile" line with three controls. Add at the top of the component body:

```tsx
  const { addToList, isListed, addToCompare, compare } = useProfileStore();
  const listed = isListed(result.university_id);
  const compareFull = compare.length >= COMPARE_LIMIT;
  const inCompare = compare.some((s) => s.id === result.university_id);
  const asListed = {
    id: result.university_id,
    name: result.name,
    fit: result.score,
    tier: result.admit_tier ?? null,
    university: result.university,
  };
```

with imports:

```tsx
import { COMPARE_LIMIT, useProfileStore } from "@/lib/profileStore";
```

Change the outer element from `<button className="card">` to `<div className="card" role="group">` and move the click handler onto a dedicated control, so nested buttons are valid HTML. Replace the closing line with:

```tsx
      <div style={{ display: "flex", gap: 8, marginTop: 14, flexWrap: "wrap" }}>
        <button type="button" className="chip" onClick={() => onOpen(result)}>
          View full profile →
        </button>
        <button
          type="button"
          className={`chip ${listed ? "on" : ""}`}
          disabled={listed}
          onClick={() => addToList(asListed)}
        >
          {listed ? "On your list" : "Add to my list"}
        </button>
        <button
          type="button"
          className={`chip ${inCompare ? "on" : ""}`}
          disabled={inCompare || compareFull}
          title={compareFull && !inCompare ? "Compare is full — remove one to add another" : undefined}
          onClick={() => addToCompare(asListed)}
        >
          {inCompare ? "Comparing" : compareFull ? "Compare full" : "Compare"}
        </button>
      </div>
```

- [ ] **Step 6: Mount the tray globally**

In `college-recommender/components/AppShell.tsx`, import and render the tray after `{children}`:

```tsx
import { CompareTray } from "@/components/CompareTray";
```

```tsx
      {children}
      <CompareTray />
```

- [ ] **Step 7: Run tests to verify they pass**

Run: `cd college-recommender && npx vitest run && npx tsc --noEmit && npx eslint app lib components`
Expected: all pass. `ResultCard.test.tsx` must be wrapped in `ProfileProvider` and its `onOpen` assertion changed to click the "View full profile" control.

- [ ] **Step 8: Commit**

```bash
git add college-recommender
git commit -m "feat: add match results, compare tray and side-by-side table"
```

---

### Task 13: The college list and its balance analysis

**Files:**
- Create: `college-recommender/lib/listAnalysis.ts`
- Create: `college-recommender/lib/listAnalysis.test.ts`
- Modify: `college-recommender/app/list/page.tsx`
- Modify: `college-recommender/components/BrowseSection.tsx`

**Interfaces:**
- Consumes: Task 8's store, Task 12's `ListedSchool`.
- Produces: `analyseList(list, SAFETY_MIN, SAFETY_MAX) -> { total, reach, target, safety, unknown, safetyShare, targetRange, needsMoreSafeties }`.

- [ ] **Step 1: Write the failing test**

Create `college-recommender/lib/listAnalysis.test.ts`:

```ts
import { describe, expect, it } from "vitest";

import { analyseList, SAFETY_MAX, SAFETY_MIN } from "./listAnalysis";
import type { ListedSchool } from "./profileStore";

const CULTURE = { collab: 0.5, quirky: 0.5, idealist: 0.5, research: 0.5, spirit: 0.5, seminar: 0.5 };

function school(id: string, tier: ListedSchool["tier"]): ListedSchool {
  return {
    id,
    name: id,
    fit: 0.8,
    tier,
    university: {
      country: "USA", location: "CA", region: "West", setting: "urban", type: "Private",
      avg_gpa: 3.7, size: "medium", majors: ["CS"], culture: CULTURE, provenance: {},
    },
  };
}

function listOf(reach: number, target: number, safety: number): ListedSchool[] {
  return [
    ...Array.from({ length: reach }, (_, i) => school(`r${i}`, "reach")),
    ...Array.from({ length: target }, (_, i) => school(`t${i}`, "target")),
    ...Array.from({ length: safety }, (_, i) => school(`s${i}`, "safety")),
  ];
}

describe("analyseList", () => {
  it("counts each tier", () => {
    const result = analyseList(listOf(8, 4, 0));

    expect(result.total).toBe(12);
    expect(result.reach).toBe(8);
    expect(result.target).toBe(4);
    expect(result.safety).toBe(0);
  });

  it("flags a list with no safeties", () => {
    const result = analyseList(listOf(8, 4, 0));

    expect(result.needsMoreSafeties).toBe(true);
    expect(result.targetRange).toEqual([2, 2]);
  });

  it("does not flag a list already inside the band", () => {
    expect(analyseList(listOf(8, 4, 3)).needsMoreSafeties).toBe(false);
  });

  it("scales the target with list size", () => {
    expect(analyseList(listOf(16, 0, 4)).targetRange).toEqual([3, 4]);
  });

  it("returns zeroes for an empty list without dividing by zero", () => {
    const result = analyseList([]);

    expect(result.total).toBe(0);
    expect(result.safetyShare).toBe(0);
    expect(result.needsMoreSafeties).toBe(false);
  });

  it("counts entries with no tier separately rather than as safeties", () => {
    const result = analyseList([school("x", null)]);

    expect(result.unknown).toBe(1);
    expect(result.safety).toBe(0);
  });

  it("uses the stated 15-20% band", () => {
    expect([SAFETY_MIN, SAFETY_MAX]).toEqual([0.15, 0.2]);
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd college-recommender && npx vitest run lib/listAnalysis.test.ts`
Expected: FAIL — `Failed to resolve import "./listAnalysis"`

- [ ] **Step 3: Write minimal implementation**

Create `college-recommender/lib/listAnalysis.ts`:

```ts
import type { ListedSchool } from "./profileStore";

/**
 * Balance of a student's college list.
 *
 * The 15-20% safety band is a stated preference, not a measured finding, and
 * copy presenting it must say so. Only the safety floor is checked: a list of
 * 20 reaches and 4 safeties passes, because over-reaching is a choice a student
 * is entitled to make knowingly.
 */
export const SAFETY_MIN = 0.15;
export const SAFETY_MAX = 0.2;

export interface ListAnalysis {
  total: number;
  reach: number;
  target: number;
  safety: number;
  /** Entries whose tier could not be computed, because no GPA was given. */
  unknown: number;
  safetyShare: number;
  targetRange: [number, number];
  needsMoreSafeties: boolean;
}

export function analyseList(list: ListedSchool[]): ListAnalysis {
  const total = list.length;
  const count = (tier: string) => list.filter((s) => s.tier === tier).length;
  const reach = count("reach");
  const target = count("target");
  const safety = count("safety");
  const unknown = list.filter((s) => !s.tier).length;

  if (total === 0) {
    return {
      total: 0, reach: 0, target: 0, safety: 0, unknown: 0,
      safetyShare: 0, targetRange: [0, 0], needsMoreSafeties: false,
    };
  }

  const safetyShare = safety / total;
  const targetRange: [number, number] = [
    Math.round(total * SAFETY_MIN),
    Math.round(total * SAFETY_MAX),
  ];

  return {
    total, reach, target, safety, unknown,
    safetyShare,
    targetRange,
    needsMoreSafeties: safetyShare < SAFETY_MIN,
  };
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd college-recommender && npx vitest run lib/listAnalysis.test.ts`
Expected: PASS, 7 tests

- [ ] **Step 5: Build the list page**

Replace `college-recommender/app/list/page.tsx`:

```tsx
"use client";

import { formatStat, tierLabel } from "@/lib/format";
import { analyseList, SAFETY_MAX, SAFETY_MIN } from "@/lib/listAnalysis";
import { useProfileStore } from "@/lib/profileStore";
import { useSchoolModal } from "@/lib/useSchoolModal";

export default function ListPage() {
  const { list, removeFromList } = useProfileStore();
  const { open, modal } = useSchoolModal();
  const analysis = analyseList(list);

  if (list.length === 0) {
    return (
      <main className="wrap">
        <section className="section">
          <h2>My college list</h2>
          <p className="lead">
            Nothing here yet. Add schools from your matches or from Browse, and we&rsquo;ll show
            you how balanced the list is.
          </p>
        </section>
      </main>
    );
  }

  return (
    <main className="wrap">
      <section className="section">
        <h2>My college list</h2>

        <div className="panel" style={{ marginBottom: 22 }}>
          <p style={{ margin: 0, fontSize: 15 }}>
            Your list is <b>{analysis.total} schools</b>: {analysis.reach} reaches,{" "}
            {analysis.target} targets, {analysis.safety} safeties
            {analysis.unknown > 0 && <> · {analysis.unknown} without a tier</>}.
          </p>

          {analysis.needsMoreSafeties ? (
            <p className="muted" style={{ marginBottom: 0, fontSize: 14 }}>
              Safeties are {Math.round(analysis.safetyShare * 100)}% of your list. A common
              suggestion is {Math.round(SAFETY_MIN * 100)}–{Math.round(SAFETY_MAX * 100)}%, about{" "}
              {analysis.targetRange[0] === analysis.targetRange[1]
                ? `${analysis.targetRange[0]} school${analysis.targetRange[0] === 1 ? "" : "s"}`
                : `${analysis.targetRange[0]}–${analysis.targetRange[1]} schools`}
              . That is a rule of thumb rather than something we measured.
            </p>
          ) : (
            <p className="muted" style={{ marginBottom: 0, fontSize: 14 }}>
              Safeties are {Math.round(analysis.safetyShare * 100)}% of your list, inside the
              usual {Math.round(SAFETY_MIN * 100)}–{Math.round(SAFETY_MAX * 100)}% suggestion.
            </p>
          )}

          {analysis.unknown > 0 && (
            <p className="muted" style={{ fontSize: 13, marginBottom: 0 }}>
              Some entries have no tier because your profile had no GPA when they were added.
            </p>
          )}
        </div>

        <div className="cards">
          {list.map((school) => {
            const price = formatStat(
              school.university.net_price,
              school.university.provenance.net_price,
              "money",
            );
            return (
              <div key={school.id} className="card" role="group">
                <div className="card-head">
                  <div>
                    <h3>{school.name}</h3>
                    <div className="loc">
                      {school.university.location} · {school.university.country} ·{" "}
                      {price.text} net
                    </div>
                  </div>
                  {tierLabel(school.tier) && (
                    <span className={`tier ${school.tier}`}>{tierLabel(school.tier)}</span>
                  )}
                </div>

                <div style={{ display: "flex", gap: 8, marginTop: 12, flexWrap: "wrap" }}>
                  <button
                    type="button" className="chip"
                    onClick={() => open({ name: school.name, university: school.university })}
                  >
                    Full profile
                  </button>
                  {school.university.url && (
                    <a
                      className="chip" href={`https://${school.university.url.replace(/^https?:\/\//, "")}`}
                      target="_blank" rel="noreferrer noopener"
                    >
                      Apply / official site ↗
                    </a>
                  )}
                  {school.university.net_price_calculator_url && (
                    <a
                      className="chip" href={school.university.net_price_calculator_url}
                      target="_blank" rel="noreferrer noopener"
                    >
                      What you&rsquo;d actually pay ↗
                    </a>
                  )}
                  <button type="button" className="chip" onClick={() => removeFromList(school.id)}>
                    Remove
                  </button>
                </div>
              </div>
            );
          })}
        </div>
      </section>
      {modal}
    </main>
  );
}
```

- [ ] **Step 6: Add "add to list" to browse rows**

In `college-recommender/components/BrowseSection.tsx`, change the row from a `<button className="card">` to a `<div className="card" role="group">` and add two controls inside it, importing the store:

```tsx
import { COMPARE_LIMIT, useProfileStore } from "@/lib/profileStore";
```

```tsx
                    <div style={{ display: "flex", gap: 8, marginTop: 12, flexWrap: "wrap" }}>
                      <button type="button" className="chip" onClick={() => onOpen(uni)}>
                        Full profile
                      </button>
                      <button
                        type="button"
                        className={`chip ${isListed(uni.id) ? "on" : ""}`}
                        disabled={isListed(uni.id)}
                        onClick={() =>
                          addToList({
                            id: uni.id, name: uni.name, fit: null, tier: null, university: uni,
                          })
                        }
                      >
                        {isListed(uni.id) ? "On your list" : "Add to my list"}
                      </button>
                      <button
                        type="button"
                        className="chip"
                        disabled={compare.length >= COMPARE_LIMIT}
                        title={
                          compare.length >= COMPARE_LIMIT
                            ? "Compare is full — remove one to add another"
                            : undefined
                        }
                        onClick={() =>
                          addToCompare({
                            id: uni.id, name: uni.name, fit: null, tier: null, university: uni,
                          })
                        }
                      >
                        Compare
                      </button>
                    </div>
```

destructuring the store at the top of the component:

```tsx
  const { addToList, isListed, addToCompare, compare } = useProfileStore();
```

- [ ] **Step 7: Run the full verification**

Run:
```bash
cd college-recommender
npx vitest run && npx tsc --noEmit && npx eslint app lib components
npm_config_cache=/tmp/npm-cache npm run build 2>&1 | grep -E "Failed|error TS|Route"
cd .. && PYBIN=.venv/bin/python ./scripts/verify.sh 2>&1 | grep -E "VERIFY|FAILED"
```
Expected: all tests pass, no lint output, four static routes plus three API routes, `VERIFY: GREEN`

- [ ] **Step 8: Verify end to end against the running stack**

Run:
```bash
cd /Users/treakybanana/Documents/College_Recommendation
open -a Docker; until docker info >/dev/null 2>&1; do sleep 1; done
docker compose up -d --build
until curl -fsS localhost:8000/healthz >/dev/null 2>&1; do sleep 2; done
curl -fsS -X POST localhost:8000/v1/activities/classify \
  -H 'content-type: application/json' \
  -d '{"name":"Science Bowl","kind":"competition","description":"built an autonomous rover"}'
curl -fsS -X POST localhost:8000/v1/recommendations \
  -H 'content-type: application/json' \
  -d '{"profile":{"gpa":3.8,"intended_major":"Computer Science","preferences":{"regions":["Northeast"],"settings":["urban"],"institution_type":"Private"}},"top_k":5}' \
  | python3 -c "
import sys, json
for r in json.load(sys.stdin)['results']:
    u = r['university']
    print(f\"  {round(r['score']*100)}%  {r['name'][:34]:<34} {u['region']:<13} {u['setting']:<9} {u['type']}\")"
```
Expected: classify returns `{"subjects":[...]}` containing `Computer Science`; every recommended school is `Northeast`, `urban` and `Private`.

- [ ] **Step 9: Commit**

```bash
git add college-recommender
git commit -m "feat: add the college list with tier-balance analysis"
```

---

## Self-Review

**Spec coverage.** Every section of the spec maps to a task: pages and persistence → 8, 9 · contract v4.0.0 → 3, 4 · region/setting scoring and the type filter → 5 · activity recognition → 7, 11 · the form → 10 · compare → 12 · the college list → 13 · data plumbing → 1, 2 · Postgres → 6. Error handling appears where it belongs rather than as its own task: corrupt `localStorage` in Task 8 Step 1, an unreachable classify endpoint in Task 11 Step 4, catalog-unreachable in the existing `useCatalog`, and entries with no tier in Task 13.

**One spec item deliberately has no task:** "a listed school leaving the catalog is shown as unavailable." `ListedSchool` stores its own `university` snapshot, so a stored entry renders from its own data and cannot dangle. The failure the spec anticipated cannot occur with this shape, so no code is needed. If the list ever stores ids alone, that task returns.

**Type consistency.** `ListedSchool` is defined once in Task 8 and consumed unchanged by 12 and 13. `in_scope(universities, scope, institution_type=None)` keeps its Task 5 signature at both call sites. `classify_activity(name, kind, description)` exists once, in scoring-service, and recommendation-service reaches it through `make_classify_fn` — so there is no second copy to drift. `COMPARE_LIMIT` is exported from `profileStore` and imported by `CompareTray`, `ResultCard` and `BrowseSection` rather than being redefined.

**Identifiers verified against the tree** rather than assumed: `_MISSING` and `parse_number` (`build_catalog.py:22,45`), `is_us` (`:82`), `CACHED_COLUMNS` (`:134`), `StatKind` including `"decimal"` and `"score"` and `tierLabel` accepting null (`lib/format.ts:11,50`), `CULTURE_AXES`, `AXIS_LABELS`, `Scope`, `AdmitTier`, `Result`, `UniversitySummary` (`lib/contract.ts`), `foldAnswers` (`lib/questionnaire.ts:102`), `MAJORS` (`lib/majors.ts:6` — not the unrelated `MAJORS` in `lib/majorsData.ts`). `Question.low`/`Question.high` exist and hold the sentence copy Task 10 renders.

**Known ordering constraint.** Task 9 creates stubs for `ProfileForm` and `/list` so the build stays green; Tasks 10 and 13 replace them. Task 10 references `MatchResults`, which Task 12 creates — the step notes to stub it if the build blocks. Running the tasks in order avoids this entirely.
