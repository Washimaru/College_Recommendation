"""Tier-2 enrichment from the College Scorecard bulk CSV.

Offline: every test uses inline fixture rows, never the 95 MB file.
See docs/superpowers/specs/2026-07-27-real-university-catalog-design.md
"""
from __future__ import annotations

from build_catalog import (
    attach_active_faculty,
    attach_details,
    attach_notable_faculty,
    coalesce_net_price,
    enrich,
    normalize_name,
    parse_number,
)


class TestNormalizeName:
    """Scorecard naming diverges from common usage in predictable ways.
    Normalization lifts exact matching from 55% to 85%."""

    def test_comma_form_matches_hyphen_form(self):
        assert normalize_name("University of California, Berkeley") == normalize_name(
            "University of California-Berkeley"
        )

    def test_en_dash_matches_hyphen(self):
        """The source dataset writes Wisconsin-Madison with an en-dash."""
        assert normalize_name("University of Wisconsin–Madison") == normalize_name(
            "University of Wisconsin-Madison"
        )

    def test_main_campus_suffix_is_stripped(self):
        assert normalize_name("Georgia Institute of Technology") == normalize_name(
            "Georgia Institute of Technology-Main Campus"
        )

    def test_distinct_schools_do_not_collide(self):
        assert normalize_name("Columbia College") != normalize_name("Columbia University")


class TestParseNumber:
    """The Scorecard missing-value marker is the literal string NA. A parser
    that only checks for empty strings reads 100% coverage where it is 16%."""

    def test_na_is_null(self):
        assert parse_number("NA") is None

    def test_empty_is_null(self):
        assert parse_number("") is None
        assert parse_number(None) is None

    def test_privacy_suppressed_is_null(self):
        assert parse_number("PrivacySuppressed") is None

    def test_real_value_parses(self):
        assert parse_number("1450") == 1450.0
        assert parse_number("0.0257") == 0.0257


class TestCoalesceNetPrice:
    """NPT4_PUB and NPT4_PRIV are public/private variants of one measure;
    a school has exactly one."""

    def test_public_school_uses_pub(self):
        assert coalesce_net_price({"NPT4_PUB": "15000", "NPT4_PRIV": "NA"}) == 15000.0

    def test_private_school_uses_priv(self):
        assert coalesce_net_price({"NPT4_PUB": "NA", "NPT4_PRIV": "32000"}) == 32000.0

    def test_both_missing_is_null(self):
        assert coalesce_net_price({"NPT4_PUB": "NA", "NPT4_PRIV": "NA"}) is None

    def test_negative_is_null_not_a_discount(self):
        """NPT4_PUB contains values like -2296. A negative net price is not a
        school paying the student; it is bad data."""
        assert coalesce_net_price({"NPT4_PUB": "-2296", "NPT4_PRIV": "NA"}) is None


NON_US = {
    "id": "university-of-oxford", "name": "University of Oxford", "country": "UK",
    "location": "Oxford", "avg_gpa": 3.9, "net_price": 30000,
    "enrollment_editorial": 12000, "majors": ["PPE"],
    "culture": {"collab": 0.5, "quirky": 0.8, "idealist": 0.6,
                "research": 0.9, "spirit": 0.4, "seminar": 0.9},
    "region": "International", "setting": "urban", "type": "Public",
}

US_ROW = {
    "UNITID": "166683", "INSTNM": "Test Tech", "CITY": "Cambridge", "STABBR": "MA",
    "ADM_RATE": "0.0400", "SAT_AVG": "1550", "UGDS": "4600",
    "NPT4_PUB": "NA", "NPT4_PRIV": "20000", "TUITIONFEE_OUT": "60000",
}


class TestEnrich:
    def test_observed_values_are_tagged_observed(self):
        record = enrich({**NON_US, "country": "USA", "name": "Test Tech"}, US_ROW)

        assert record["avg_sat"] == 1550
        assert record["acceptance_rate"] == 0.04
        assert record["provenance"]["avg_sat"] == "observed"
        assert record["provenance"]["acceptance_rate"] == "observed"

    def test_scorecard_overrides_editorial_net_price(self):
        record = enrich({**NON_US, "country": "USA"}, US_ROW)

        assert record["net_price"] == 20000
        assert record["provenance"]["net_price"] == "observed"

    def test_unmatched_school_keeps_editorial_values_as_nulls(self):
        record = enrich(NON_US, None)

        assert record["avg_sat"] is None
        assert record["acceptance_rate"] is None
        assert record["enrollment"] is None
        assert record["net_price"] == 30000
        assert record["provenance"]["net_price"] == "editorial"

    def test_non_us_sat_is_not_applicable_not_absent(self):
        """The SAT is not used outside the US. Marking it `absent` would invite
        someone to 'fix' it by inventing a number."""
        record = enrich(NON_US, None)

        assert record["provenance"]["avg_sat"] == "not_applicable"

    def test_avg_gpa_always_comes_from_tier_one(self):
        """No public source publishes admitted GPA."""
        record = enrich({**NON_US, "country": "USA"}, US_ROW)

        assert record["avg_gpa"] == 3.9
        assert record["provenance"]["avg_gpa"] == "editorial"


class TestCache:
    """The committed cache keeps builds reproducible and offline after the
    first fetch, and small enough to review in a diff."""

    def test_cache_keeps_only_rows_the_catalog_uses(self):
        from build_catalog import filter_cache

        index = {
            normalize_name("Test Tech"): US_ROW,
            normalize_name("Irrelevant College"): {**US_ROW, "INSTNM": "Irrelevant College"},
        }
        tier1 = [
            {"name": "Test Tech", "country": "USA"},
            {"name": "University of Oxford", "country": "UK"},
        ]

        cache = filter_cache(tier1, index, {})

        assert list(cache) == [normalize_name("Test Tech")]

    def test_cache_keeps_only_columns_the_catalog_reads(self):
        from build_catalog import CACHED_COLUMNS, filter_cache

        index = {normalize_name("Test Tech"): {**US_ROW, "IRRELEVANT_COL": "x"}}
        cache = filter_cache([{"name": "Test Tech", "country": "USA"}], index, {})

        assert set(cache[normalize_name("Test Tech")]) <= set(CACHED_COLUMNS)
        assert "IRRELEVANT_COL" not in cache[normalize_name("Test Tech")]

    def test_cache_resolves_aliases(self):
        from build_catalog import filter_cache

        index = {normalize_name("Columbia University in the City of New York"): US_ROW}
        cache = filter_cache(
            [{"name": "Columbia University", "country": "USA"}],
            index,
            {"Columbia University": "Columbia University in the City of New York"},
        )

        assert len(cache) == 1


class TestDetails:
    """Curated per-school profiles (scholarships, research, outcomes, grad and
    professional schools). Coverage is partial and uneven - the schools without
    one carry nothing rather than generated filler. The live count is generated
    into `catalogStats.ts`, not quoted here, because it moves with the catalog."""

    def test_curated_details_are_attached_and_marked(self):
        record = enrich({**NON_US, "country": "USA"}, US_ROW)
        merged = attach_details(
            record,
            {"university-of-oxford": {"outcomes": {"gradRate": "98%"}, "_source": "curated"}},
        )

        assert merged["details"]["outcomes"]["gradRate"] == "98%"
        assert merged["provenance"]["details"] == "observed"

    def test_school_without_details_gets_none_not_filler(self):
        record = enrich(NON_US, None)
        merged = attach_details(record, {})

        assert merged["details"] is None
        assert merged["provenance"]["details"] == "absent"

    def test_web_verified_details_are_marked_distinctly(self):
        record = enrich(NON_US, None)
        merged = attach_details(
            record, {"university-of-oxford": {"outcomes": {}, "_source": "web_verified"}}
        )

        assert merged["provenance"]["details"] == "web_verified"

    def test_estimated_details_are_marked_editorial(self):
        record = enrich(NON_US, None)
        merged = attach_details(
            record, {"university-of-oxford": {"outcomes": {}, "_source": "estimated"}}
        )

        assert merged["provenance"]["details"] == "editorial"


OUTCOME_ROW = {
    **US_ROW,
    "C150_4": "0.9412", "MD_EARN_WNE_P10": "112000", "MD_EARN_WNE_P6": "89000",
    "GRAD_DEBT_MDN": "21500", "PCTPELL": "0.1834", "PCTFLOAN": "0.2711",
}


class TestOutcomes:
    """Federal outcome data: graduation rate, median earnings and debt.
    Observed, not estimated, and available for 97-99% of matched US schools."""

    def test_outcomes_are_extracted_and_marked_observed(self):
        record = enrich({**NON_US, "country": "USA"}, OUTCOME_ROW)

        assert record["outcomes"]["graduation_rate"] == 0.9412
        assert record["outcomes"]["median_earnings_10yr"] == 112000
        assert record["outcomes"]["median_debt"] == 21500
        assert record["provenance"]["outcomes"] == "observed"

    def test_unmatched_school_has_no_outcomes(self):
        record = enrich(NON_US, None)

        assert record["outcomes"] is None
        assert record["provenance"]["outcomes"] == "absent"

    def test_partial_outcome_data_keeps_what_exists(self):
        row = {**OUTCOME_ROW, "MD_EARN_WNE_P10": "NA", "GRAD_DEBT_MDN": "NA"}
        record = enrich({**NON_US, "country": "USA"}, row)

        assert record["outcomes"]["graduation_rate"] == 0.9412
        assert record["outcomes"]["median_earnings_10yr"] is None

    def test_all_outcome_fields_missing_yields_none(self):
        row = {k: ("NA" if k.startswith(("C150", "MD_EARN", "GRAD_DEBT", "PCT")) else v)
               for k, v in OUTCOME_ROW.items()}
        record = enrich({**NON_US, "country": "USA"}, row)

        assert record["outcomes"] is None
        assert record["provenance"]["outcomes"] == "absent"


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


class TestTuitionInState:
    """Spec B. The out-of-state figure alone misstates a public university by
    tens of thousands of dollars: Alabama is $12,180 in state and $34,172 out.
    Both come from the same Scorecard row the catalog already reads — no IPEDS
    join, contrary to the plan that asked for this."""

    def test_both_tuition_figures_are_carried(self):
        record = enrich(
            {**NON_US, "country": "USA"},
            {**US_ROW, "TUITIONFEE_IN": "12180", "TUITIONFEE_OUT": "34172"},
        )

        assert record["tuition_in_state"] == 12180
        assert record["sticker_tuition"] == 34172

    def test_an_absent_in_state_price_is_null_not_the_out_of_state_one(self):
        record = enrich(
            {**NON_US, "country": "USA"},
            {**US_ROW, "TUITIONFEE_IN": "NULL", "TUITIONFEE_OUT": "34172"},
        )

        assert record["tuition_in_state"] is None
        assert record["provenance"]["tuition_in_state"] == "absent"

    def test_it_is_observed_when_present(self):
        record = enrich(
            {**NON_US, "country": "USA"}, {**US_ROW, "TUITIONFEE_IN": "12180"}
        )

        assert record["provenance"]["tuition_in_state"] == "observed"

    def test_a_non_us_school_has_no_in_state_price_to_report(self):
        """"In-state" is a US concept; abroad it does not apply, which must
        read differently from a missing US figure."""
        record = enrich(NON_US, None)

        assert record["tuition_in_state"] is None
        assert record["provenance"]["tuition_in_state"] == "not_applicable"


class TestProgramsAwarded:
    """Spec C. The editorial `majors` list names a school's strengths, so
    absence from it proves nothing — reading it that way would have the catalog
    claim MIT has no philosophy department. Scorecard's PCIP columns are the
    share of degrees a school actually awards, so they can carry that claim."""

    def test_awarded_programs_are_named_and_shared(self):
        record = enrich(
            {**NON_US, "country": "USA"},
            {**US_ROW, "PCIP11": "0.25", "PCIP14": "0.5", "PCIP38": "0"},
        )

        assert record["programs"] == [
            {"name": "Engineering", "share": 0.5},
            {"name": "Computer & Information Sciences", "share": 0.25},
        ]

    def test_a_zero_share_is_omitted_rather_than_listed_as_zero(self):
        record = enrich({**NON_US, "country": "USA"}, {**US_ROW, "PCIP38": "0"})

        assert all(p["name"] != "Philosophy & Religious Studies" for p in record["programs"])

    def test_an_empty_list_means_awards_none_of_these(self):
        """Distinct from null: an empty list is a school Scorecard measured
        and found awarding nothing in these families, which is what makes
        "does not offer X" sayable at all."""
        record = enrich({**NON_US, "country": "USA"}, {**US_ROW, "PCIP11": "0"})

        assert record["programs"] == []
        assert record["provenance"]["programs"] == "observed"

    def test_no_scorecard_row_means_unknown_not_empty(self):
        record = enrich({**NON_US, "country": "USA"}, None)

        assert record["programs"] is None
        assert record["provenance"]["programs"] == "absent"

    def test_a_non_us_school_is_not_applicable(self):
        record = enrich(NON_US, None)

        assert record["programs"] is None
        assert record["provenance"]["programs"] == "not_applicable"


class TestState:
    """The school's state, structured.

    `location` ("Ann Arbor, MI") is display-only by rule — never a filter,
    never a scoring input — so residency cannot be decided by parsing it.
    STABBR is already in the cached columns and is the honest source.
    """

    def test_a_us_school_carries_its_state(self):
        record = enrich({**NON_US, "country": "USA"}, {**US_ROW, "STABBR": "MI"})

        assert record["state"] == "MI"

    def test_a_non_us_school_has_no_state(self):
        record = enrich(NON_US, None)

        assert record["state"] is None
        assert record["provenance"]["state"] == "not_applicable"

    def test_a_us_school_with_no_scorecard_row_is_absent_not_guessed(self):
        record = enrich({**NON_US, "country": "USA"}, None)

        assert record["state"] is None
        assert record["provenance"]["state"] == "absent"


class TestNotableFaculty:
    """Named professors per school, from faculty-pipeline's notable stage.

    The tier file records what was looked up; this only attaches it. The
    distinction that matters is the same one `programs` draws: a school that
    was searched and yielded nobody is not a school nobody searched.
    """

    TIER = {
        "test-tech": {
            "school_id": "test-tech",
            "school_name": "Test Tech",
            "notable_faculty": [
                {"name": "Jane Doe", "known_for": "American physicist", "fields": ["physicist"],
                 "status": "current", "prominence": 12, "source": "wikipedia",
                 "source_url": "https://en.wikipedia.org/wiki/Jane_Doe"},
            ],
        },
        "searched-empty": {
            "school_id": "searched-empty", "school_name": "Empty College",
            "notable_faculty": [],
        },
    }

    def test_a_school_with_faculty_carries_the_list(self):
        record = attach_notable_faculty(
            {**enrich({**NON_US, "country": "USA"}, US_ROW), "id": "test-tech"}, self.TIER
        )

        assert record["notable_faculty"][0]["name"] == "Jane Doe"
        assert record["provenance"]["notable_faculty"] == "web_verified"

    def test_a_searched_school_with_nobody_gets_an_empty_list(self):
        record = attach_notable_faculty(
            {**enrich({**NON_US, "country": "USA"}, US_ROW), "id": "searched-empty"}, self.TIER
        )

        assert record["notable_faculty"] == []
        assert record["provenance"]["notable_faculty"] == "web_verified"

    def test_an_unsearched_school_is_null_not_empty(self):
        record = attach_notable_faculty(
            {**enrich({**NON_US, "country": "USA"}, US_ROW), "id": "never-looked"}, self.TIER
        )

        assert record["notable_faculty"] is None
        assert record["provenance"]["notable_faculty"] == "absent"

    def test_a_non_us_school_is_not_applicable(self):
        record = attach_notable_faculty(enrich(NON_US, None), self.TIER)

        assert record["notable_faculty"] is None
        assert record["provenance"]["notable_faculty"] == "not_applicable"

    def test_no_contact_details_are_ever_attached(self):
        """The published field carries who someone is, never how to reach
        them — that line is what keeps the faculty CSVs gitignored."""
        tier = {"test-tech": {"notable_faculty": [
            {"name": "Jane Doe", "email": "jane@test.edu", "phone": "555-1234",
             "known_for": "physicist", "fields": [], "status": "current",
             "prominence": 3, "source": "wikipedia", "source_url": "https://x"},
        ]}}

        record = attach_notable_faculty(
            {**enrich({**NON_US, "country": "USA"}, US_ROW), "id": "test-tech"}, tier
        )

        person = record["notable_faculty"][0]
        assert "email" not in person and "phone" not in person
        assert person["name"] == "Jane Doe"


class TestActiveFaculty:
    """Researchers publishing from the school now, with what they work on.

    Distinct from notable_faculty, which answers "who is famous here" and
    includes people who died decades ago. Same three states as every other
    measured field: a list, [] for searched-and-found-nobody, null for
    unsearched.
    """

    TIER = {
        "test-tech": {
            "school_id": "test-tech",
            "active_faculty": [
                {"name": "Jim Wiseman",
                 "research": ["Mathematical Dynamics and Fractals"],
                 "fields": ["Mathematics"], "recent_works": 8, "last_active": 2026,
                 "source": "openalex", "source_url": "https://openalex.org/A1"},
            ],
        },
        "searched-empty": {"school_id": "searched-empty", "active_faculty": []},
    }

    def test_a_school_with_researchers_carries_them(self):
        record = attach_active_faculty(
            {**enrich({**NON_US, "country": "USA"}, US_ROW), "id": "test-tech"}, self.TIER
        )

        person = record["active_faculty"][0]
        assert person["name"] == "Jim Wiseman"
        assert person["research"] == ["Mathematical Dynamics and Fractals"]
        assert record["provenance"]["active_faculty"] == "observed"

    def test_searched_and_empty_differs_from_unsearched(self):
        searched = attach_active_faculty(
            {**enrich({**NON_US, "country": "USA"}, US_ROW), "id": "searched-empty"}, self.TIER
        )
        unsearched = attach_active_faculty(
            {**enrich({**NON_US, "country": "USA"}, US_ROW), "id": "nobody-looked"}, self.TIER
        )

        assert searched["active_faculty"] == []
        assert unsearched["active_faculty"] is None
        assert unsearched["provenance"]["active_faculty"] == "absent"

    def test_a_non_us_school_is_not_applicable(self):
        record = attach_active_faculty(enrich(NON_US, None), self.TIER)

        assert record["active_faculty"] is None
        assert record["provenance"]["active_faculty"] == "not_applicable"

    def test_only_the_published_fields_survive(self):
        """An allowlist, so a field added upstream cannot leak into a public
        catalog by nobody noticing — the same guard notable_faculty has."""
        tier = {"test-tech": {"active_faculty": [
            {"name": "Jim Wiseman", "research": [], "fields": [], "recent_works": 3,
             "last_active": 2026, "source": "openalex", "source_url": "https://openalex.org/A1",
             "orcid": "0000-0001", "email": "jim@test.edu"},
        ]}}

        record = attach_active_faculty(
            {**enrich({**NON_US, "country": "USA"}, US_ROW), "id": "test-tech"}, tier
        )

        person = record["active_faculty"][0]
        assert "email" not in person and "orcid" not in person


class TestTheAllowlistLetsThroughWhatWasAdded:
    """The allowlist blocks fields nobody declared, which is the point — but
    it also silently drops ones that were added deliberately. Awards and
    h-index reached the tier files and stopped at this boundary, which would
    have shown up as a UI that renders nothing for data that exists.
    """

    def test_notable_awards_survive(self):
        tier = {"test-tech": {"notable_faculty": [
            {"name": "Eric Lander", "known_for": "American geneticist", "fields": [],
             "status": "current", "prominence": 40,
             "awards": ["Grace Murray Hopper Award", "National Medal of Technology"],
             "source": "wikipedia", "source_url": "https://en.wikipedia.org/wiki/Eric_Lander"},
        ]}}

        record = attach_notable_faculty(
            {**enrich({**NON_US, "country": "USA"}, US_ROW), "id": "test-tech"}, tier
        )

        assert record["notable_faculty"][0]["awards"] == [
            "Grace Murray Hopper Award", "National Medal of Technology",
        ]

    def test_active_h_index_and_awards_survive(self):
        tier = {"test-tech": {"active_faculty": [
            {"name": "Laureate Lee", "research": ["Quantum Optics"], "fields": ["Physics"],
             "recent_works": 3, "last_active": 2026, "h_index": 62,
             "awards": ["Nobel Prize in Physics"],
             "source": "openalex", "source_url": "https://openalex.org/A1"},
        ]}}

        record = attach_active_faculty(
            {**enrich({**NON_US, "country": "USA"}, US_ROW), "id": "test-tech"}, tier
        )

        person = record["active_faculty"][0]
        assert person["h_index"] == 62
        assert person["awards"] == ["Nobel Prize in Physics"]

    def test_a_contact_detail_is_still_blocked(self):
        """Widening the allowlist must not widen it to everything."""
        tier = {"test-tech": {"active_faculty": [
            {"name": "Laureate Lee", "h_index": 62, "awards": [], "email": "lee@test.edu",
             "source": "openalex", "source_url": "https://openalex.org/A1"},
        ]}}

        record = attach_active_faculty(
            {**enrich({**NON_US, "country": "USA"}, US_ROW), "id": "test-tech"}, tier
        )

        assert "email" not in record["active_faculty"][0]
