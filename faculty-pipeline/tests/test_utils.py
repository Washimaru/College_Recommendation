from __future__ import annotations

from faculty_pipeline.utils import extract_text_excerpt, slugify

# -- extract_text_excerpt -----------------------------------------------------
#
# This is the new Stage 2 logic (M3b): turn a cached HTML page into the
# plain-text evidence handed to classify_directory. The three cases below are
# exactly the discrimination the model needs to make -- a list of people, a
# list of departments, and a dead-end search box -- so each must produce a
# visibly different excerpt.

HTML_PERSON_LIST = """
<html>
<head><title>Faculty</title></head>
<body>
  <nav><a href="/">Home</a><a href="/about">About</a></nav>
  <header><a href="/login">Login</a></header>
  <main>
    <h1>Department of Computer Science Faculty</h1>
    <ul>
      <li><a href="/faculty/jane-doe">Jane Doe, Professor</a></li>
      <li><a href="/faculty/john-smith">John Smith, Associate Professor</a></li>
      <li><a href="/faculty/amy-chen">Amy Chen, Assistant Professor</a></li>
    </ul>
  </main>
  <footer><a href="/privacy">Privacy</a></footer>
</body>
</html>
"""

HTML_DEPARTMENT_LIST = """
<html>
<head><title>Directory</title></head>
<body>
  <nav><a href="/">Home</a></nav>
  <main>
    <h1>Campus Directory</h1>
    <ul>
      <li><a href="/directory/chemistry">Chemistry</a></li>
      <li><a href="/directory/economics">Economics</a></li>
      <li><a href="/directory/physics">Physics</a></li>
    </ul>
  </main>
</body>
</html>
"""

HTML_SEARCH_BOX_ONLY = """
<html>
<head><title>People Search</title></head>
<body>
  <nav><a href="/">Home</a></nav>
  <main>
    <h1>Find a Person</h1>
    <form action="/search">
      <input type="text" name="q" placeholder="Enter a name">
      <button type="submit">Search</button>
    </form>
  </main>
</body>
</html>
"""


def test_person_list_excerpt_surfaces_names_in_link_text() -> None:
    excerpt = extract_text_excerpt(HTML_PERSON_LIST, max_chars=4000)

    assert "Jane Doe" in excerpt
    assert "John Smith" in excerpt
    assert "Amy Chen" in excerpt


def test_department_list_excerpt_surfaces_department_names_not_people() -> None:
    excerpt = extract_text_excerpt(HTML_DEPARTMENT_LIST, max_chars=4000)

    assert "Chemistry" in excerpt
    assert "Economics" in excerpt
    assert "Physics" in excerpt
    # The discriminator the prompt relies on: no personal names appear.
    assert "Jane Doe" not in excerpt


def test_search_box_only_excerpt_has_no_person_or_department_links() -> None:
    excerpt = extract_text_excerpt(HTML_SEARCH_BOX_ONLY, max_chars=4000)

    assert "Find a Person" in excerpt
    assert "Jane Doe" not in excerpt
    assert "Chemistry" not in excerpt
    # No <a> tags on this page at all besides nav (stripped), so there is no
    # "Links:" section carrying list-of-people signal.
    assert "Links:" not in excerpt


def test_nav_and_footer_boilerplate_is_dropped() -> None:
    excerpt = extract_text_excerpt(HTML_PERSON_LIST, max_chars=4000)

    assert "Login" not in excerpt
    assert "Privacy" not in excerpt
    assert "About" not in excerpt


def test_excerpt_is_capped_at_max_chars() -> None:
    long_html = "<html><body><p>" + ("faculty name filler text. " * 500) + "</p></body></html>"

    excerpt = extract_text_excerpt(long_html, max_chars=200)

    assert len(excerpt) <= 200


def test_excerpt_is_deterministic_for_the_same_input() -> None:
    first = extract_text_excerpt(HTML_PERSON_LIST, max_chars=4000)
    second = extract_text_excerpt(HTML_PERSON_LIST, max_chars=4000)

    assert first == second


def test_empty_html_returns_empty_excerpt_without_raising() -> None:
    assert extract_text_excerpt("", max_chars=4000) == ""
    assert extract_text_excerpt("   ", max_chars=4000) == ""


def test_duplicate_link_text_is_not_repeated() -> None:
    html = (
        "<html><body><main>"
        '<a href="/a">Jane Doe</a><a href="/b">Jane Doe</a>'
        "</main></body></html>"
    )

    excerpt = extract_text_excerpt(html, max_chars=4000)

    assert excerpt.count("Jane Doe") == 1


# -- slugify (pre-existing, sanity-check import path is untouched) -----------


def test_slugify_still_works() -> None:
    assert slugify("Acme Tech!") == "acme-tech"
