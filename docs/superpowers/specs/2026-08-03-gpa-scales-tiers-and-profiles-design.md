# GPA Scales, a Fourth Tier, and Deeper US Profiles — Design

**Date:** 2026-08-03
**Status:** approved (decisions taken 2026-08-03)

## Context

Three requests, one of which carries a fabrication risk worth naming up front.

1. Students report GPA on different scales. Today the form takes one number and
   compares it straight against a school's editorial `avg_gpa`, which is on an
   unweighted 4.0 scale. A student entering `4.42` from a weighted 5.0 scale is
   silently treated as having a 4.42 unweighted — well above every school in the
   catalog — and every tier they are shown is wrong.
2. `reach | target | safety` collapses two very different situations. A school
   where the student is somewhat below average, and a school that rejects 96% of
   everyone, are both "reach".
3. US school profiles should carry signature research areas and notable faculty.

## Decision 1 — two GPA fields, no conversion

```
gpa           required, 0.0-4.0    unweighted. Scored. Drives admit tiers.
gpa_weighted  optional, 0.0-5.0    weighted. Displayed. Never scored, never converted.
```

**There is deliberately no conversion between them.** A 4.42/5.0 is not
`4.42 × 0.8`, and it is not `4.42 − 0.5`: high schools weight differently, cap
differently, and include different course sets. Any formula would be invented
precision of exactly the kind this codebase refuses elsewhere (see the 15–20%
safety band, which is labelled a rule of thumb because it is one).

So the student is asked for both, and told plainly which one is scored. If they
only know their weighted GPA, they enter it and leave the unweighted field to
their best estimate — that is honest guessing by the person who actually knows
their transcript, rather than dishonest arithmetic by us.

`gpa_weighted` is **not** added to the scoring rubric. The gap between weighted
and unweighted is a genuine course-rigor signal, but we have no evidence for what
weight it deserves, and inventing one would move every ranking on a number we
made up. It is displayed as context, and that is all.

## Decision 2 — `extreme_reach`, keyed on selectivity not GPA

```
extreme_reach   acceptance_rate <= 0.15
reach           school avg_gpa - student gpa >=  0.12
safety          school avg_gpa - student gpa <= -0.12
target          otherwise
```

Precedence: `extreme_reach` first, then the existing GPA rule.

Selectivity, not GPA gap, is what makes a school an extreme reach. At a 4%
admit rate, a 4.0 student is still rejected far more often than not — telling
them it is a "target" because their GPA clears the average is the single most
misleading thing this product could say. The threshold is 15%, and like the
safety band it is **a stated judgement, not a measured finding**; the copy must
present it that way.

`acceptance_rate` is null for every non-US school and some US ones. Those keep
falling through to the GPA rule, and `extreme_reach` simply never fires — an
absent rate must not manufacture a tier, exactly as elsewhere.

Existing tier semantics are unchanged, so `admit_tier` stays a breaking contract
change only because a new enum member is added.

### Consequences for the college list

`analyseList` gains an `extremeReach` count. The 15–20% safety floor is
unchanged and still the only thing checked — over-reaching remains a choice a
student is entitled to make knowingly. Extreme reaches are *reported*, never
warned about.

## Decision 3 — research and faculty for all 268 US schools

Coverage today: `research` 29 schools, `faculty` 6.

**These must be researched, not generated.** Naming a professor is a factual
claim about a real, identifiable person; attributing a paper or a prize to them
is a claim about their record. Model recall is not a source for this: faculty
move, retire and die, and the assistant's knowledge has a cutoff. A plausible
name attached to the wrong university is precisely the failure a 17-year-old
would never catch and would act on.

Rules, matching the scholarship research already in this repo:

- Every entry carries a `src` URL, preferably the institution's own page.
- Faculty entries name people who are **currently** affiliated, and carry a
  "faculty change — verify" caveat, as the existing MIT entry does.
- A school with nothing verifiable gets **no section**, not a hedged one.
  Absent sections already simply do not render.
- Batches report a hit rate, as the scholarship research did.

`details` is free-form JSON and already contains both keys, so this needs no
contract change — only data and rendering.

## Contract v5.0.0

Breaking twice over: `admit_tier` gains an enum member and `Profile` gains a
field. Five mirrors move together, or it is H3 drift:

`docs/contracts/*.schema.json` · both services' `schemas.py` ·
`gateway/src/types.ts` · `college-recommender/lib/contract.ts`

## Testing

- A weighted GPA never changes a score or a tier — only what is displayed.
- `gpa_weighted` is optional; its absence changes nothing.
- `extreme_reach` fires on a 4% school even for a 4.0 student.
- `extreme_reach` never fires when `acceptance_rate` is null.
- The four tiers are mutually exclusive and total.
- `analyseList` counts extreme reaches separately and does not fold them into
  reaches for the safety-floor maths.
- Every researched faculty/research entry has a `src`.
