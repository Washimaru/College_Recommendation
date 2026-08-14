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
