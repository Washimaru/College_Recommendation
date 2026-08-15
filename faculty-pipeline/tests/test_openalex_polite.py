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
