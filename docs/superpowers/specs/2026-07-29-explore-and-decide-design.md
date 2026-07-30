# Explore & Decide — Design

**Date:** 2026-07-29
**Spec:** A of three. B (in-state cost + residency) and C (deep school profiles)
are separate and not covered here.
**Status:** design, approved section by section

## Context

The site currently gathers a real profile and returns ranked schools, but it
stops there. A student cannot compare candidates, cannot keep a list of the
schools they are actually considering, and cannot filter by where a school is or
what kind of place it is. Match, Browse and Major Finder share one page, so
moving between them feels like scrolling one long document rather than using
three tools.

The purpose this spec serves, in the author's words: a student should put in
their real profile and then *explore* — encountering universities they would
never have thought of, seeing many schools' information in one place rather than
researching one at a time, and understanding which ones actually fit. Informative
and investigative. Guidable but not generic.

Success: a student can go from a blank form to a rated, saved list of schools
they intend to apply to, having compared candidates side by side, without losing
their work and without ever seeing a figure the catalog cannot support.

## Scope

In: real page separation with a persisted profile · a form that does not read as
a tax return · region, campus-setting and public/private filtering · richer
activity input with subject recognition · side-by-side comparison · a college
list with balance analysis and gap suggestions · student-body composition where
it exists.

Out, and deliberately: in-state tuition and residency mix (spec B — both need an
IPEDS join Scorecard does not provide); famous faculty, notable research,
graduate and professional school detail, 3+2 and five-year programmes, club
activity levels, regional industry (spec C — all sit at 1-8% coverage or do not
exist in any dataset).

Also out, and this one is a refusal rather than a deferral: **"which majors a
school does not offer" cannot be built from our data.** The `majors` field holds
a median of six editorial *strengths*, not a course catalog. Deriving absence
from it would claim MIT does not offer Philosophy, Political Science,
Architecture or Chemistry — all real MIT departments. The honest route is
Scorecard's 38 `PCIP*` columns, where a genuine zero means no degrees awarded in
that family; that belongs to spec C.

## Pages and persistence

Four routes replace the current tab bar:

```
/         Your profile      the form, and where matches appear
/browse   Browse            search all 358
/majors   Major Finder
/list     My college list   the list you build, rated
```

Real routes reintroduce a problem tabs were chosen to avoid: navigating away
would discard eight questionnaire answers and several typed activities. So the
profile and the college list live in **one React context mirrored to
`localStorage`**, surviving navigation, refresh and closing the tab. No backend,
no accounts.

The trade-off, stated plainly because it will surprise someone: `localStorage`
is per-browser, so a list built on a laptop does not appear on a phone. Buying
that would mean accounts and a `profiles` table, which is a different project.

Adding a school to the list is available wherever a school appears — match card,
browse row, compare view, profile modal — because collecting candidates while
exploring is the behaviour the site exists to support.

## Contract v4.0.0

A major bump. Required fields are added and one field is removed; both break a
stale client, and the version should say so. Four artefacts move in one change:
`docs/contracts/{profile,score,recommendation}.schema.json`, both Python
`schemas.py` mirrors, and `services/gateway/src/types.ts`. Splitting them is H3
drift.

### University gains six fields

| Field | Values | Coverage |
|---|---|---|
| `region` | Northeast, South, West, Midwest, International | 100% |
| `setting` | urban, suburban, rural | 100% |
| `type` | Public, Private | 100% |
| `population` | `{international_share, women_share, first_gen_share}` or null | US only |

The first three already exist on all 358 records in
`sources/unimatch_catalog.json` and are silently dropped by `enrich()`, which
builds a fresh dict and never copies them. This is plumbing, not research.

`population` comes from Scorecard `UGDS_NRA`, `UGDS_WOMEN` and `FIRST_GEN`
(100%, 100% and 93% of matched US schools). It is **absent for non-US schools**,
not zeroed and not estimated: `provenance.population` reads `not_applicable` and
the UI renders nothing.

Also added, both from Scorecard at 100% coverage:

- `url` — the institution's own site (`INSTURL`)
- `net_price_calculator_url` — (`NPCURL`), where a student finds what *they*
  would pay rather than the population average we store

### University.location is display-only

`location` holds strings like `"Cambridge, MA"`. It stays, unchanged, purely so a
card can show where a school is. It is **never** a filter or a scoring input.

### Profile.preferences changes shape

```
regions:           string[]                        NEW, soft
settings:          string[]                        NEW, soft
institution_type:  "Public" | "Private" | null     NEW, hard
locations:         string[]                        REMOVED
```

`locations` is removed rather than kept. It compared against `uni.location`, so
firing it required a student to type an exact city string — it could not work in
practice. Carrying a field that cannot work is worse than a breaking change.

### Activity gains `description`

The explanation box. It feeds **recognition**, not extra scoring weight: see
below.

## Scoring changes

### Region and setting are soft; type is hard

Region and setting fold into the existing `fit` dimension rather than becoming
new dimensions, which avoids rebalancing six weights again:

```
fit = 0.50 x major  +  0.25 x region match  +  0.25 x setting match
```

Each match term is defined precisely, since "match" against a list is otherwise
open to two readings:

```
region match  = 1.0 if preferences.regions is empty          (no preference)
                1.0 if uni.region  is in preferences.regions
                0.0 otherwise
setting match = same rule against preferences.settings
```

An unstated preference therefore scores 1.0 rather than 0.5. That is deliberate
and differs from the culture axes: culture uses importance weighting, where an
untouched axis drops out of the average entirely. Here the term is a fixed 0.25
of `fit`, so scoring it 0.5 when unstated would silently cost every student an
eighth of the dimension for a question they chose not to answer.

`institution_type` is a hard filter applied at candidate selection alongside
`scope`, so a requested `top_k` is still filled.

The soft/hard split is deliberate and follows the reference project. 28 of 358
schools are rural; a student expressing a mild setting preference must not
silently lose 92% of the catalog. "Public only", by contrast, is a real
constraint about cost and scale, and should mean what it says.

### Activity recognition

New endpoint `POST /v1/activities/classify` returns the subject families matched
for a given name, kind and description, using the **same** `_ACTIVITY_SUBJECTS`
table the scorer uses. One implementation, so what the student is shown is
exactly what the scorer will do — which matters, because that feedback is a
promise about how their answer will be used.

Rejected alternatives: shipping the pattern table to the client (duplicates
regex evaluation in two languages) and copying the table into the UI (guarantees
drift on the first edit to either side).

`description` is included in the text the matcher reads, so "I wrote the code
for our robot's autonomous vision system" is recognised even when the name field
says something the 14 patterns miss. Note the description must still hit one of
the 14 existing patterns — the table is not widened, so a description in wholly
unrecognised vocabulary stays unrecognised, and the UI says so rather than
pretending otherwise. **Each activity still contributes at
most one hit**, which `activity_fit` already enforces by breaking on first match.
Elaboration therefore helps a genuinely relevant activity be *recognised*, but
stuffing five subjects into one box cannot out-score five real activities.

## The form

The current form is five input boxes, then eight rows of five identical chip
buttons, then a text field with an Add button. It reads as a tax return.

It becomes a **vertical sequence of cards, one question per card**. Numbers stay
as numeric inputs. The eight preference questions become full-width cards with
two labelled halves you click — *"Fine, I compete"* against *"I'd rather we
helped each other"* — plus a middle "either". The thing you click is the
sentence, not an anonymous dot on an unlabelled scale. Region and setting become
labelled tiles you toggle.

Everything stays visible on one scrollable page. A wizard was considered and
rejected: hiding fields behind step navigation works against a tool meant to be
investigated rather than completed.

Activity entry gains the explanation box and shows recognition inline:

```
FIRST Robotics            [competition]
  -> recognised as: Engineering, Computer Science
Science Bowl              [competition]
  -> not recognised. Tell us what you did and we will try again.
  [ explanation ......................................... ]
```

The unrecognised case is the one that matters. It tells the student the site did
not understand, rather than silently scoring nothing, and gives them the means to
fix it.

## Compare

A tray pinned to the bottom of the viewport holds up to **three** slots, filled
from anywhere a school appears. Pressing Compare opens a side-by-side table of
fit, tier, GPA and SAT, acceptance, net price, undergraduates, international
share and the six culture axes.

Three and not more: a fourth column stops fitting a laptop, and the purpose is
deciding between finalists rather than building a spreadsheet.

When the tray is full, the Add control on every card shows as **disabled with a
reason** ("compare is full — remove one to add another") rather than silently
replacing the oldest entry. Evicting a school the student deliberately chose,
without saying so, is the worse failure.

Every cell renders through `lib/format.ts`, so `n/a` and an em dash stay
distinguishable and a missing figure never reads as zero.

## The college list

`/list` shows what the student has collected, persisted with the profile. Each
entry carries its tier, its fit, and two real links — the institution's site and
its net price calculator.

### Balance analysis

```
Your list is 12 schools: 8 reaches, 4 targets, 0 safeties.
Safeties are 0% of your list - aim for 15-20%, about 2 schools.
From your matches, these would be safeties for you:
  Grinnell (92% fit) - Whitman (88%) - Denison (85%)
```

Tier counts come from `admit_tier`, already computed server-side. The safety
target is `round(n x 0.15)` to `round(n x 0.20)`, flagged only when the actual
share falls below 15%.

Two honesty constraints on the copy:

- The **15-20% band is a stated preference, not a measured finding.** It is
  presented as a suggestion. A student must not read an invented threshold as
  something we derived from data.
- Suggestions are drawn only from schools the student has actually been matched
  with. Never invented, and never a school they have shown no interest in.

Only the safety floor is constrained. A list of 20 reaches and 4 safeties passes:
over-reaching is a choice a student is entitled to make knowingly.

## Error handling

- **Catalog unreachable** — browse and compare already distinguish a 503 from an
  empty result. That behaviour extends to the list page, which must never imply
  a school has no data when the service is simply down.
- **Classification endpoint unreachable** — activity entry degrades to accepting
  the text without showing recognition. It must not block submission; the scorer
  performs its own matching regardless.
- **Corrupt `localStorage`** — a malformed stored profile is discarded and the
  form starts empty, with a notice. A parse error must not white-screen the app.
- **A listed school leaving the catalog** — deduplication and defunct-school
  removal already dropped six schools once. A stored list entry whose id no
  longer resolves is shown as unavailable with an explanation, not silently
  deleted.

## Testing

Python, offline as always:

- `region`, `setting`, `type` and `population` survive `enrich()` into the
  catalog; `population` is absent for non-US and marked `not_applicable`.
- `fit` scores region and setting neutrally when unstated, and rewards a match.
- `institution_type` filters before ranking, so `top_k` is still filled.
- `classify` returns the same families the scorer matches, for the same input —
  the property that keeps one implementation honest.
- `description` improves recognition without raising a single activity's
  contribution above one hit.

TypeScript:

- Profile and list survive a simulated navigation; a corrupt stored value falls
  back to empty rather than throwing.
- Balance analysis: 0 safeties in 12 flags with a target of 2; 3 safeties in 15
  does not flag; an empty list produces no guidance rather than a division by
  zero.
- Compare renders three columns and refuses a fourth.
- Suggestions never include a school already on the list.
- A null stat renders as an em dash or `n/a` in the compare table, never `0`.

## Implementation order

1. Contract v4.0.0 and the data plumbing, with scoring changes.
2. The classify endpoint.
3. Routing, the profile context and `localStorage` persistence.
4. The form rebuild.
5. Compare tray and table.
6. The college list and its analysis.

Stages 1 and 2 are backend and independently verifiable by `scripts/verify.sh`.
Stages 3 to 6 are frontend and depend on 1.
