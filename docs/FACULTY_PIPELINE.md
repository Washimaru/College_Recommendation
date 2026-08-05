# Faculty Data Pipeline — Implementation Plan

A Python pipeline that reads `school_details.json`, filters to U.S. universities,
discovers each school's official faculty directory, crawls professor profiles,
normalizes the extracted fields with an LLM, and writes per-university CSVs plus
one master CSV.

This document is written so it can be executed step-by-step with the **Claude
Code CLI** — each module maps to a self-contained build task, and the "Building
with Claude Code" section at the end gives exact prompts and a milestone order.

> **Adapted for this repo (2026-08-04).** This plan was written against
> `University_Recommendation_Project`. Two deviations, both deliberate:
>
> 1. **Input is the catalog, not `school_details.json`.** Stage 1 needs
>    `country`/`homepage`; `school_details.json` here holds only detail sections
>    (`academics`, `admissions`, `faculty`…) keyed by school id. The catalog
>    (`data-pipeline/out/universities.json`, rebuildable from committed sources)
>    carries `country`, `location` and `url` for all 268 US schools.
>    `school_details.json` is joined in for passthrough.
> 2. **No search API key is configured.** Stage 2 runs heuristics first, as §6
>    specifies, and the search adapter degrades to a no-op rather than failing.
>
> The package lives at `faculty-pipeline/`, a sibling of `data-pipeline/`.

---

## 1. Goals & Scope

**Input:** `school_details.json` — the exported school dataset (the same profiles
that back the `js/details.js` layer of the UniMatch site).

**Output:**

- `output/by_school/<slug>.csv` — one CSV per university.
- `output/master.csv` — all professors across all schools, concatenated.

**In scope:** U.S. universities only. Official faculty/department directories
only (no third-party aggregators like RateMyProfessors). Public profile fields:
name, title, department, email, phone, research interests, profile URL.

**Out of scope:** authentication-gated pages, PDF-only CVs (logged as skipped),
non-U.S. institutions, personal data beyond publicly listed directory fields.

**Guiding principles**

- **Idempotent & resumable.** Every stage checkpoints; re-running skips finished
  work. A crash costs one page, not the whole run.
- **Polite crawling.** Respect `robots.txt`, rate-limit per host, identify with a
  descriptive User-Agent, cache every fetch.
- **LLM only where it earns its keep.** Deterministic parsing first; the LLM is
  used for messy normalization and field extraction from unstructured HTML, not
  as a crawler.
- **Separation of stages.** Raw HTML, parsed rows, and normalized rows are
  distinct artifacts on disk, so any stage can be re-run in isolation.

---

## 2. Architecture Overview

Five sequential stages, each reading the previous stage's on-disk artifact and
writing its own. Stages communicate through files (not memory), which is what
makes the pipeline resumable.

```
school_details.json
        │
        ▼
┌─────────────────────┐
│ 1. LOAD & FILTER    │  parse JSON → keep US schools → normalized school records
└─────────────────────┘
        │  data/schools.jsonl
        ▼
┌─────────────────────┐
│ 2. DISCOVER         │  find each school's official faculty-directory URL(s)
│    DIRECTORIES      │  (search + heuristics + robots check)
└─────────────────────┘
        │  data/directories.jsonl
        ▼
┌─────────────────────┐
│ 3. CRAWL PROFILES   │  fetch directory pages → enumerate profile links →
│                     │  fetch each professor page → store raw HTML
└─────────────────────┘
        │  cache/html/…  +  data/profiles_raw.jsonl
        ▼
┌─────────────────────┐
│ 4. EXTRACT &        │  deterministic parse → LLM normalization →
│    NORMALIZE (LLM)  │  validated professor records
└─────────────────────┘
        │  data/profiles_clean.jsonl
        ▼
┌─────────────────────┐
│ 5. EXPORT CSV       │  per-school CSVs + master.csv
└─────────────────────┘
        │
        ▼
output/by_school/*.csv  +  output/master.csv
```

Cross-cutting services used by every stage: a caching HTTP client, a rate
limiter, a structured logger, and a checkpoint store.

---

## 3. Directory Structure

```
University_Recommendation_Project/
├── pipeline.md                  # this document
├── school_details.json          # input (may be generated from js/details.js)
│
├── faculty_pipeline/            # the Python package
│   ├── __init__.py
│   ├── __main__.py              # enables `python -m faculty_pipeline`
│   ├── cli.py                   # argparse/click entrypoint, subcommands
│   ├── config.py                # dataclass config, env + YAML loading
│   │
│   ├── stages/
│   │   ├── __init__.py
│   │   ├── load_filter.py       # Stage 1
│   │   ├── discover.py          # Stage 2
│   │   ├── crawl.py             # Stage 3
│   │   ├── extract.py           # Stage 4 (deterministic parse + LLM)
│   │   └── export.py            # Stage 5
│   │
│   ├── services/
│   │   ├── __init__.py
│   │   ├── http_client.py       # cached, rate-limited, retrying fetcher
│   │   ├── robots.py            # robots.txt fetch + allow/deny cache
│   │   ├── search.py            # web-search adapter for directory discovery
│   │   ├── llm.py               # LLM client wrapper (structured output)
│   │   ├── checkpoint.py        # resumable state store
│   │   └── logging_setup.py     # structured logging config
│   │
│   ├── models.py                # dataclasses / pydantic schemas
│   └── utils.py                 # slugify, url helpers, text cleaning
│
├── prompts/
│   ├── extract_professor.txt    # LLM extraction/normalization prompt
│   └── classify_directory.txt   # LLM directory-link classification prompt
│
├── config/
│   └── pipeline.yaml            # tunable defaults (rate limits, model, paths)
│
├── data/                        # intermediate artifacts (JSONL), git-ignored
│   ├── schools.jsonl
│   ├── directories.jsonl
│   ├── profiles_raw.jsonl
│   └── profiles_clean.jsonl
│
├── cache/                       # git-ignored
│   ├── html/                    # raw fetched pages, keyed by URL hash
│   ├── search/                  # cached search responses
│   └── llm/                     # cached LLM responses (prompt hash → result)
│
├── checkpoints/                 # git-ignored; per-stage progress + failures
│   ├── discover.json
│   ├── crawl.json
│   └── extract.json
│
├── output/                      # deliverables
│   ├── by_school/
│   │   └── <slug>.csv
│   └── master.csv
│
├── logs/
│   └── run-<timestamp>.log
│
├── tests/
│   ├── test_load_filter.py
│   ├── test_discover.py
│   ├── test_crawl.py
│   ├── test_extract.py
│   ├── test_export.py
│   └── fixtures/                # saved HTML + JSON samples for offline tests
│
├── requirements.txt
├── .env.example                 # ANTHROPIC_API_KEY, SEARCH_API_KEY, etc.
└── README_pipeline.md           # short run instructions
```

Add `data/`, `cache/`, `checkpoints/`, `logs/`, `.env` to `.gitignore`.

---

## 4. Data Schemas

All intermediate artifacts are **JSONL** (one JSON object per line) — append-only
and easy to resume. Final artifacts are CSV.

### 4.1 School record — `data/schools.jsonl`

```json
{
  "school_id": "mit",
  "name": "Massachusetts Institute of Technology",
  "slug": "massachusetts-institute-of-technology",
  "country": "US",
  "state": "MA",
  "homepage": "https://www.mit.edu",
  "control": "private",
  "source_fields": { "...": "passthrough of original details fields" }
}
```

### 4.2 Directory record — `data/directories.jsonl`

```json
{
  "school_id": "mit",
  "directory_urls": [
    "https://www.eecs.mit.edu/people/faculty-advisors/",
    "https://math.mit.edu/directory/faculty/"
  ],
  "discovery_method": "search+heuristic",
  "robots_allowed": true,
  "confidence": 0.86,
  "notes": "department-level directories; no single campus-wide page found"
}
```

### 4.3 Raw profile record — `data/profiles_raw.jsonl`

```json
{
  "school_id": "mit",
  "profile_url": "https://math.mit.edu/directory/profile?id=123",
  "directory_url": "https://math.mit.edu/directory/faculty/",
  "html_cache_path": "cache/html/9f86d0818.html",
  "fetched_at": "2026-08-04T18:22:10Z",
  "http_status": 200,
  "parse_hint": { "name": "Jane Doe", "title": "Professor" }
}
```

### 4.4 Clean professor record — `data/profiles_clean.jsonl` and CSV columns

| Column | Type | Notes |
|---|---|---|
| `school_id` | str | FK to schools |
| `school_name` | str | denormalized for the CSV |
| `professor_name` | str | required; row dropped if missing |
| `title` | str | e.g., "Associate Professor" |
| `department` | str | normalized department name |
| `email` | str | validated / de-obfuscated where possible |
| `phone` | str | E.164-ish normalized when present |
| `research_interests` | str | semicolon-separated list |
| `profile_url` | str | canonical source URL |
| `directory_url` | str | where the profile was found |
| `extraction_confidence` | float | 0–1, from LLM |
| `extracted_at` | ISO8601 | timestamp |

The master CSV is the union of all per-school rows with identical columns.

---

## 5. Modules & Responsibilities

### 5.1 `config.py`

A frozen dataclass holding all tunables, loaded from `config/pipeline.yaml` with
environment-variable overrides. Keys: `input_path`, `output_dir`, `data_dir`,
`cache_dir`, `rate_limit_per_host` (default 1 req/2s), `max_concurrency`,
`request_timeout`, `max_retries`, `user_agent`, `llm_model`, `llm_max_tokens`,
`search_provider`, `max_profiles_per_school` (safety cap), `respect_robots`
(default true).

### 5.2 `services/http_client.py`

The single fetch path for the whole pipeline. Responsibilities: check the HTML
cache first (keyed by SHA-256 of the URL); if missed, acquire a per-host
rate-limit token, send the request with the configured User-Agent and timeout,
retry on 429/5xx with exponential backoff + jitter, persist the body to
`cache/html/`, and return `(status, final_url, body, from_cache)`. Never fetches
a URL disallowed by `robots.py`.

### 5.3 `services/robots.py`

Fetches and caches each host's `robots.txt`, exposes `is_allowed(url, agent)`.
Also surfaces any `Crawl-delay` so the rate limiter can honor it.

### 5.4 `services/search.py`

Adapter over a web-search API (pluggable: Brave, Bing, SerpAPI, or a
`WebSearch`-style provider). Given a school name, returns candidate URLs for
"official faculty directory". Responses are cached under `cache/search/`.

### 5.5 `services/llm.py`

Wraps the LLM (Anthropic Messages API by default). Two calls:
`classify_directory(candidates, school)` → picks/ranks the official directory
URL(s); and `extract_professor(text, url, school)` → returns the structured
professor record. Enforces a JSON schema (tool/structured output), caches by
prompt hash under `cache/llm/`, and bounds cost with `llm_max_tokens`.

### 5.6 `services/checkpoint.py`

A tiny JSON-backed store per stage: `is_done(key)`, `mark_done(key, meta)`,
`mark_failed(key, error)`. Keys are school IDs (discover) or profile URLs
(crawl/extract). This is what makes every stage resumable.

### 5.7 Stage modules (`stages/*.py`)

Each exposes `run(config, checkpoint, logger) -> Summary` and is independently
invocable via the CLI. Details in §6.

### 5.8 `models.py`

Dataclasses/pydantic models for `School`, `Directory`, `RawProfile`,
`Professor`, plus a `StageSummary` (counts of processed / skipped / failed).

---

## 6. Execution Flow (per stage)

### Stage 1 — Load & Filter (`load_filter.py`)

1. Read `school_details.json` (stream if large).
2. For each school, determine country. Keep only U.S. schools — detect via an
   explicit country field if present, else a `state` in the 50 states + DC, else
   a `.edu` homepage as a weak signal (log low-confidence keeps).
3. Normalize into the School schema; assign a stable `school_id`/`slug`.
4. Write `data/schools.jsonl`. Dedupe by slug.

**Failure modes:** malformed JSON (fail fast, exit non-zero); ambiguous country
(keep + flag). Idempotent: overwrites `schools.jsonl` deterministically.

### Stage 2 — Discover Directories (`discover.py`)

1. For each school not already in `checkpoints/discover.json`:
   - Try heuristic URLs first (`{homepage}/faculty`, `/people`,
     `/directory`, `/academics/faculty`) and check which resolve.
   - Query `search.py` for `"<school> official faculty directory"`.
   - Hand candidates to `llm.classify_directory` to pick official,
     on-domain directory URL(s) and reject aggregators.
   - Check `robots.py` for each chosen URL.
2. Append to `data/directories.jsonl`; `mark_done(school_id)`.

**Failure modes:** no directory found (record empty `directory_urls`, mark done
with `confidence: 0`); search API error (retry, then mark failed → retried on
next run). Resumable per school.

### Stage 3 — Crawl Profiles (`crawl.py`)

1. For each directory URL: fetch (via cached client), then enumerate candidate
   professor-profile links. Enumeration strategy: same-domain anchors matching
   profile patterns (`/faculty/`, `/people/`, `/profile`, `?id=`), plus
   pagination follow ("next", numbered pages) up to a page cap. De-duplicate.
2. For each profile URL not already crawled: fetch, store HTML in cache, append
   a RawProfile row with a light `parse_hint` (name/title guessed from `<title>`
   or headings). Enforce `max_profiles_per_school`.
3. `mark_done(profile_url)` after each successful fetch.

**Failure modes:** 404/dead links (log + skip), infinite pagination (page cap),
JS-rendered directories where static HTML yields no links (flag school as
`needs_dynamic_render`; optionally fall back to a headless-browser fetch behind a
config flag). Resumable per profile URL.

### Stage 4 — Extract & Normalize (`extract.py`)

1. For each RawProfile not in `checkpoints/extract.json`:
   - **Deterministic pass:** strip HTML to readable text; pull obvious fields
     with selectors/regex (mailto: emails, `tel:` phones, meta tags, JSON-LD
     `Person` blocks). De-obfuscate common email patterns ("name [at] mit.edu").
   - **LLM pass:** send cleaned text + deterministic hints to
     `llm.extract_professor`, which returns the structured Professor record with
     a confidence score. The LLM normalizes titles, splits research interests,
     and fills gaps the deterministic pass missed.
   - **Validate:** require `professor_name`; validate email/phone formats; drop
     or flag rows failing validation.
2. Append to `data/profiles_clean.jsonl`; `mark_done(profile_url)`.

**Failure modes:** LLM returns invalid JSON (schema-validate + one repair retry,
then skip + log), profile page is a stub with no person data (low confidence →
excluded from CSV but kept in JSONL for audit). Cached by prompt hash, so
re-runs are nearly free.

### Stage 5 — Export CSV (`export.py`)

1. Read `data/profiles_clean.jsonl`, group by `school_id`.
2. Filter to rows meeting a min-confidence threshold (config).
3. Write `output/by_school/<slug>.csv` per school (stable column order, UTF-8).
4. Concatenate all rows into `output/master.csv`.
5. Print a `StageSummary`: schools, professors, skipped, failed.

---

## 7. Command-Line Interface

`click`/`argparse` with one subcommand per stage plus `all`.

```
python -m faculty_pipeline [GLOBAL OPTS] <command> [OPTS]

Global options
  --config PATH          config/pipeline.yaml (default)
  --input PATH           override school_details.json path
  --log-level LEVEL      DEBUG|INFO|WARNING|ERROR  (default INFO)
  --dry-run              plan only; no network / no writes

Commands
  load                   Stage 1: load & filter US schools
  discover               Stage 2: find faculty directories
      --limit N          process at most N schools
      --school ID        run a single school
  crawl                  Stage 3: crawl professor profiles
      --limit N
      --school ID
      --dynamic          enable headless-browser fallback
  extract                Stage 4: extract + LLM-normalize
      --school ID
      --no-llm           deterministic pass only (debug)
  export                 Stage 5: write per-school + master CSVs
  all                    run stages 1→5 in order
      --resume           skip checkpointed work (default true)
      --force            ignore checkpoints and reprocess

  status                 print checkpoint/progress summary
  clean                  clear cache/checkpoints (with --yes)
```

Examples:

```bash
# Full run, resumable
python -m faculty_pipeline all

# Iterate on one school end-to-end
python -m faculty_pipeline discover --school mit
python -m faculty_pipeline crawl    --school mit --limit 25
python -m faculty_pipeline extract  --school mit
python -m faculty_pipeline export

# Re-extract everything without re-crawling (uses HTML cache)
python -m faculty_pipeline extract --force
```

---

## 8. Error Handling & Resilience

**Layered strategy**

- **Transient (network/timeouts/429/5xx):** retry in `http_client` with
  exponential backoff + jitter, capped at `max_retries`; honor `Retry-After`.
- **Per-item failures:** never abort the run. Catch, log with context, record in
  the stage checkpoint as `failed`, and continue. Failed items are retried on the
  next run automatically.
- **Fatal (bad config, missing input, missing API key):** fail fast at startup
  with a clear message and non-zero exit.

**Logging.** Structured logs to `logs/run-<ts>.log` and console. Each line
carries stage, school_id, url, and outcome. A run ends with a summary table.

**Politeness & compliance.** Respect `robots.txt` and `Crawl-delay`; per-host
rate limiting; descriptive User-Agent with contact URL; only official `.edu`/
on-domain directories; collect only publicly listed directory fields. Skipped
domains and disallowed paths are logged, not bypassed.

**Cost & safety caps.** `max_profiles_per_school`, LLM `max_tokens`, LLM response
caching, and `--dry-run` keep both crawl volume and API spend bounded.

---

## 9. Checkpoints & Resumability

- Each stage owns a JSON checkpoint (`checkpoints/<stage>.json`) mapping item
  keys → `{status, attempts, last_error, updated_at}`.
- Item keys: `school_id` (discover), `profile_url` (crawl, extract).
- **On start,** a stage loads its checkpoint and skips `done` items unless
  `--force`.
- **Artifacts are append-only JSONL**, so a crash mid-write loses at most the
  current line; a startup pass can compact/dedupe.
- **HTML and LLM caches** mean re-running extract after a crawl, or export after
  extract, does no network or API work.
- `status` command aggregates all checkpoints into a progress report
  (done/failed/pending per stage).

Result: interrupting the run at any point and re-running `all` continues exactly
where it stopped.

---

## 10. Dependencies

```
# requirements.txt
httpx               # async HTTP with timeouts + HTTP/2
selectolax          # fast HTML parsing (or beautifulsoup4 + lxml)
tenacity            # retry/backoff
pydantic            # schema validation
click               # CLI
pyyaml              # config
anthropic           # LLM client (structured output)
python-dotenv       # .env loading
tldextract          # domain/robots helpers
# optional:
playwright          # headless fallback for JS-rendered directories
```

Secrets via `.env` (see `.env.example`): `ANTHROPIC_API_KEY`, `SEARCH_API_KEY`.

---

## 11. Testing

- **Unit, offline-first.** Every stage tested against saved fixtures in
  `tests/fixtures/` — sample `school_details.json`, saved directory HTML, saved
  profile HTML — so tests never hit the network or the LLM (mock `llm.py` and
  `http_client.py`).
- **Key cases:** US/non-US filtering; slug/dedupe; directory heuristic matching;
  link enumeration + pagination cap; email de-obfuscation; LLM-JSON validation
  and repair path; CSV column order and UTF-8 encoding; checkpoint skip/force.
- **Smoke test:** `--dry-run all` on the real input plans the full run with no
  side effects.
- **Golden CSV:** a small fixed input asserts an exact `master.csv` output.

---

## 12. Building with Claude Code CLI

This plan is structured so each module is a discrete, testable build task. Work
in milestones; commit after each. Suggested prompts to Claude Code, in order:

**Milestone 0 — scaffold**
> "Create the `faculty_pipeline` package, directory tree, `requirements.txt`,
> `config/pipeline.yaml`, `.env.example`, and `.gitignore` entries exactly as in
> pipeline.md §3. Add empty stage/service modules with typed function stubs and
> the `models.py` dataclasses from §4."

**Milestone 1 — services**
> "Implement `services/http_client.py`, `robots.py`, `checkpoint.py`, and
> `logging_setup.py` per §5 and §8–9. Include unit tests with mocked HTTP."

**Milestone 2 — Stage 1**
> "Implement `stages/load_filter.py` per §6 Stage 1 and wire the `load` CLI
> command. Add tests using `tests/fixtures/school_details.sample.json`."

**Milestone 3 — Stage 2**
> "Implement `services/search.py`, `services/llm.py` (classify_directory), and
> `stages/discover.py` per §6 Stage 2. Cache search + LLM calls. Add tests that
> mock both."

**Milestone 4 — Stage 3**
> "Implement `stages/crawl.py`: link enumeration, pagination cap, robots checks,
> HTML caching, per-profile checkpoints (§6 Stage 3). Add tests on saved HTML."

**Milestone 5 — Stage 4**
> "Implement `stages/extract.py`: deterministic parse + email de-obfuscation +
> JSON-LD, then `llm.extract_professor` with schema validation and one repair
> retry (§6 Stage 4). Add the extraction prompt in `prompts/`."

**Milestone 6 — Stage 5 + `all`**
> "Implement `stages/export.py` and the `all`/`status`/`clean` commands. Add the
> golden-CSV test and a `--dry-run` smoke test."

**Working style with Claude Code**

- Run `python -m faculty_pipeline <stage> --school mit --limit 5` after each
  milestone to validate on one school before scaling.
- Keep the LLM prompts in `prompts/` as files so they can be edited without
  touching code.
- Commit per milestone; the checkpoints let you stop and resume across sessions.
- Ask Claude Code to run `pytest` after each module and fix failures before
  moving on.

---

## 13. Open Decisions

- **Directory granularity:** campus-wide vs. per-department directories. Default:
  accept multiple department directories when no single campus page exists.
- **Dynamic rendering:** enable Playwright fallback globally or per-flagged
  school. Default: off, opt-in via `--dynamic`.
- **Confidence threshold** for including a professor row in the CSV. Default:
  0.5, tunable in config.
- **Search provider** choice and quota. Default: pluggable adapter, configured in
  `pipeline.yaml`.
