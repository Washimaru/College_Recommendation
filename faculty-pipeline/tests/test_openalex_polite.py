from faculty_pipeline.services.openalex import polite_user_agent


class TestThePoliteAddressTravelsInTheHeader:
    """OpenAlex documents the polite pool as a `mailto:` in the User-Agent.
    Putting it in the query string works too, but the HTTP cache is keyed on
    the URL — so a mailto there changes every cache key and silently discards
    every response already on disk. The header carries it at no such cost.
    """

    def test_the_address_is_folded_into_the_user_agent(self):
        agent = polite_user_agent("UniMatchBot/0.1", "person@example.edu")
        assert "mailto:person@example.edu" in agent
        assert agent.startswith("UniMatchBot/0.1")

    def test_no_address_leaves_the_agent_untouched(self):
        assert polite_user_agent("UniMatchBot/0.1", None) == "UniMatchBot/0.1"

    def test_the_url_never_carries_the_address(self, tmp_path):
        """The whole point: a cached URL must not depend on who is asking."""
        from faculty_pipeline.services.openalex import OpenAlexApi

        seen = []

        class Fetcher:
            def fetch(self, url, *, method="GET"):
                seen.append(url)
                class R:
                    body = "{}"

                return R()

        OpenAlexApi(Fetcher(), mailto="person@example.edu").get("authors", search="x")
        assert "mailto" not in seen[0], seen[0]


class TestTheClientIsActuallyBuiltWithIt:
    """The unit tests above cover `polite_user_agent` in isolation, which is
    exactly why the first wiring shipped broken: it called `model_copy` on a
    frozen dataclass and blew up only when the CLI ran. This asserts the
    config the HTTP client receives really carries the address.
    """

    def test_a_config_can_be_rebuilt_with_the_polite_agent(self):
        import dataclasses

        from faculty_pipeline.config import Config

        base = Config(input_path="schools.csv")
        polite = dataclasses.replace(
            base, user_agent=polite_user_agent(base.user_agent, "person@example.edu")
        )

        assert "mailto:person@example.edu" in polite.user_agent
        assert polite.input_path == base.input_path
        assert "mailto" not in base.user_agent, "the original must not be mutated"


class TestInstitutionsMatchOnTheRegistrableDomain:
    """Homepage matching was exact on host+path, which rejected 19 schools
    whose OpenAlex homepage differs only by subdomain:

        dartmouth.edu            vs home.dartmouth.edu
        newbrunswick.rutgers.edu vs rutgers.edu
        www.howard.edu           vs www2.howard.edu

    All three were the top search hit and plainly correct. Comparing the
    registrable domain accepts them while still rejecting the failure this
    check exists for — a search for "Berklee" returning Google.
    """

    def test_a_subdomain_does_not_break_the_match(self):
        from faculty_pipeline.services.openalex import registrable_domain

        assert registrable_domain("https://dartmouth.edu/") == \
               registrable_domain("https://home.dartmouth.edu")
        assert registrable_domain("www.howard.edu/") == \
               registrable_domain("http://www2.howard.edu/")

    def test_a_different_institution_still_fails(self):
        from faculty_pipeline.services.openalex import registrable_domain

        assert registrable_domain("https://www.berklee.edu") != \
               registrable_domain("https://www.google.ca")

    def test_a_compound_suffix_keeps_three_labels(self):
        """ox.ac.uk must not reduce to ac.uk, which every UK school shares."""
        from faculty_pipeline.services.openalex import registrable_domain

        assert registrable_domain("https://www.ox.ac.uk") == "ox.ac.uk"
        assert registrable_domain("https://www.cam.ac.uk") != \
               registrable_domain("https://www.ox.ac.uk")


class TestAConfidentNameMatchIsAcceptedWhenDomainsDisagree:
    """Schools change domains and the pipeline's copy goes stale. Indiana
    Bloomington is `indiana.edu` here and `iu.edu` at OpenAlex; UNC Charlotte
    rebranded from `uncc.edu` to `charlotte.edu`. Both are unambiguously the
    right institution and both were dropped.

    Homepage stays the primary signal. The fallback accepts a search hit whose
    *name* matches exactly once normalised — which still rejects the case this
    guard exists for, a search for "Berklee" returning "Google".
    """

    def _api(self, results):
        import json as _json

        class Fetcher:
            def fetch(self, url, *, method="GET"):
                class R:
                    body = _json.dumps({"results": results})
                return R()

        from faculty_pipeline.services.openalex import OpenAlexApi
        return OpenAlexApi(Fetcher())

    def test_a_stale_domain_no_longer_loses_the_school(self):
        api = self._api([{"id": "https://openalex.org/I1",
                          "display_name": "Indiana University Bloomington",
                          "homepage_url": "https://bloomington.iu.edu"}])

        found = api.institution_for("Indiana University Bloomington", "https://www.indiana.edu/")

        assert found is not None and found["id"].endswith("I1")

    def test_a_different_institution_is_still_rejected(self):
        api = self._api([{"id": "https://openalex.org/I2", "display_name": "Google",
                          "homepage_url": "https://www.google.ca"}])

        assert api.institution_for("Berklee College of Music", "https://www.berklee.edu") is None

    def test_a_near_miss_name_is_not_good_enough(self):
        """"University of Miami" must not absorb "Miami University" — different
        schools in different states."""
        api = self._api([{"id": "https://openalex.org/I3", "display_name": "Miami University",
                          "homepage_url": "https://miamioh.edu"}])

        assert api.institution_for("University of Miami", "https://welcome.miami.edu") is None
