# Active faculty — research plan and design

**The question.** Not "who is famous here" — which `notable_faculty` already
answers, and answers with dead people — but "who is teaching and researching
here *now*, and what are they working on". A student choosing a school wants
someone whose class they could take.

## Why the existing field cannot answer it

`notable_faculty` comes from Wikipedia category membership. Two problems, both
structural rather than fixable:

- **Notability is not currency.** The category "MIT faculty" holds everyone who
  ever taught there. Its `status` field says only whether a date of death is
  recorded — Chomsky is alive and listed at MIT, and has been at Arizona since
  2017.
- **Occupations are not research.** Wikidata gives "biologist"; a student wants
  "single-cell transcriptomics".

## Sources evaluated

| Source | Current? | Research topics? | Cost | Verdict |
|---|---|---|---|---|
| **OpenAlex** | yes — publication dates and affiliation years | yes — topic/subfield/field hierarchy | free, no key | **chosen** |
| The school's own directory | yes — a directory lists current staff | yes, in prose | needs LLM credits (exhausted) + ~45h crawling | later; schema leaves room |
| ORCID | employment records with dates | keywords, sparsely filled | free | thinner than OpenAlex; revisit for job titles |
| Wikipedia | no | no | free | already used, for a different question |

OpenAlex is CC0, needs no API key (only a `mailto` in the User-Agent), and
carries exactly the two things missing: *when* someone was affiliated, and
*what they research*.

## Three failure modes found while measuring, and the guard for each

Each of these was observed on real data, not anticipated in the abstract.

**1. `last_known_institutions` collides on names.** ArtCenter College of
Design's most-cited "authors" were Jie Wang, Lijuan Zhou and Wenshu Wu, working
on epigenetics and cellulose. Their own affiliation records name Chinese
universities and never mention ArtCenter — OpenAlex derives this field from the
most recent raw affiliation string, and "Art Center" is a common phrase.
→ *Guard:* never use `last_known_institutions`. Ask instead which authors
appear on papers **written from** the institution.

**2. Ever-affiliated is not currently-affiliated.** Filtering on
`affiliations.institution.id` and sorting by citations gave MIT: Eric Lander,
then **Yoshua Bengio** — a postdoc there in 1991–92, at Montreal ever since.
→ *Guard:* require a publication from that institution within the last three
years.

**3. OpenAlex sometimes mis-attributes an entire body of work.** With the
*correct* Berklee College of Music id, the API returns 80 recent papers whose
titles are "JWST/NIRCam Probes Young Star Clusters in the Reionization Era".
A music college has not started doing gravitational lensing.
→ *Guard:* a plausibility check against the school's own degree data. Every
OpenAlex topic carries a `field` ("Physics and Astronomy", "Mathematics"), and
this catalog already knows which CIP families each school actually awards
degrees in. An author whose fields match nothing the school teaches is dropped.
Berklee awards Visual & Performing Arts, so the astronomers go.

**4. Institution resolution must be verified, not searched.** A bare name search
for "Berklee" returned *Google (Canada)*. → *Guard:* resolve by matching
OpenAlex's `homepage_url` against the catalog's own `url`, with the name search
only as a fallback whose result must then agree on homepage or ROR.

## What the pipeline does

1. Resolve each US school to an OpenAlex institution, by homepage.
2. Ask for works published **from** that institution since `year - 3`, grouped
   by author — this is the "who is here now" signal.
3. Fetch those authors for their topics, works count and last active year.
4. Drop anyone whose research fields match nothing the school awards degrees in.
5. Keep the top ~20 by recent output at that school.

## What it publishes, and what it does not claim

```jsonc
"active_faculty": [
  {
    "name": "Jim Wiseman",
    "research": ["Mathematical Dynamics and Fractals", "Advanced Topology and Set Theory"],
    "fields": ["Mathematics"],          // OpenAlex field, used for the major filter
    "recent_works": 8,                  // papers from this school since the cutoff
    "last_active": 2026,
    "source": "openalex",
    "source_url": "https://openalex.org/A…"
  }
]
```

**No contact details**, as with `notable_faculty`.

**It does not claim the word "professor".** OpenAlex knows who publishes from an
institution, not who holds a teaching appointment: the list will include some
postdocs and research staff, and will miss faculty who do not publish — studio
art, performance, clinical teaching. The UI says "researching here now", which
is what the data supports. The school's own directory is the only source that
can say "Associate Professor of English", and it is credit-blocked; the schema
carries a `source` per entry so those merge in later without a contract change.

## The other half of the request

Historical faculty move out of the main list into their own section of the
school profile, so the default view answers "who could teach me" and the people
who are no longer there are still available, one click away, rather than mixed
in.
