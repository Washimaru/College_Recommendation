# Notable faculty — design

**Goal.** For every US school in the catalog, a list of named professors — 10–20
where the sources support it — with enough about each to be worth reading: what
they do, and a link to verify it.

## What exists today, measured

- `details.faculty` covers **81 of 268** US schools, and it is one prose
  sentence, not a list. MIT's names four people inside a paragraph.
- `faculty-pipeline/` crawls official directories and produces exactly the right
  shape (name, title, department, research interests, profile URL) — but has
  reached **8 schools** and its extract stage is **blocked on API credits**
  (verified again 2026-08-13: `credit balance is too low`).

## The constraint that decides the design

Extraction from directory prose needs an LLM, and there are no credits. So the
first source has to be one that is **structured enough to need no model at
all** — which also means it cannot invent a professor, the one failure this
feature must never have.

## Sources

**A. Wikipedia + Wikidata (this pass).** Every school has a
`Category:<School> faculty`, and it is populated at every tier — measured:
MIT 500+, Michigan 500+, Bard 204, Spelman 65, ArtCenter 28, Agnes Scott 13.
Each page resolves to a Wikidata item giving:

| field | from |
|---|---|
| is this a person at all | `P31 = Q5` |
| what they are known for | English description, e.g. "American linguist" |
| living or historical | `P570` (date of death) |
| how widely known | count of language Wikipedias holding an article |
| occupation / field | `P106` |

No API key, no model, and every row carries a Wikidata QID and a Wikipedia URL,
so every claim is checkable by a reader.

Wikidata's SPARQL endpoint is unusable (throttled to 1 request/minute during an
active outage), so this goes through the ordinary MediaWiki API — which needs
polite serialised access: a burst of 60 requests gets a 429. That is precisely
what `faculty-pipeline/services/http_client.py` already provides (per-host rate
limit, on-disk cache, backoff), so the stage reuses it rather than reinventing.

**B. The school's own directory (already built, credit-blocked).** Stages 1–5
give real full-time faculty with titles and research interests. Its
deterministic path (`extract --no-llm`, JSON-LD / meta / mailto) works with no
credits and is run here over the 596 already-crawled profiles, to prove the
merge. Extending it to all 268 schools needs credits plus roughly 45 hours of
polite crawling (measured in Phase 3), so it lands later — the schema carries a
per-entry `source` so it can, without another contract change.

## What gets published, and what does not

Name, what they are known for, field, a source URL, and whether they are current
or historical. **No email, no phone.** The existing rule — faculty CSVs stay
gitignored because `master.csv` aggregates hundreds of academics' contact
details — is about contact details, not about the fact that a named professor
teaches somewhere. That fact is already published by the school, by Wikipedia,
and by this catalog's own `details.faculty`.

## Honesty rules

- A school with fewer than 10 findable professors gets the shorter list. Nothing
  is padded, and nothing is generated.
- Historical faculty are kept but **labelled** — Ansel Adams (ArtCenter, d. 1984)
  and Chinua Achebe (Bard, d. 2013) are much of why those schools are known, and
  the UI must never imply they still teach.
- `null` means unmeasured; `[]` means looked and found none. Same rule as
  `programs`.

## Shape

```jsonc
"notable_faculty": [
  {
    "name": "Noam Chomsky",
    "known_for": "American linguist and political activist",  // Wikidata description
    "fields": ["linguist", "philosopher"],                    // P106 labels
    "status": "historical" | "current",                       // P570 present or not
    "prominence": 178,                                        // language editions
    "source": "wikipedia",                                    // or "directory"
    "source_url": "https://en.wikipedia.org/wiki/Noam_Chomsky"
  }
]
```

Ranked by `prominence` so the recognisable names lead, capped at 20.

## Route

1. `faculty-pipeline`: new `notable` stage + CLI command, reusing the existing
   HTTP client, cache and checkpoints.
2. Run for all 268 US schools; write `data-pipeline/sources/notable_faculty.json`
   — a committed tier file, like every other input, since it holds no contact
   details and must be reproducible offline.
3. `build_catalog.py` attaches it to each school.
4. Contract **v9.0.0** across the five mirrors, the DB schema, the loader, the
   read path, and the school profile UI.
