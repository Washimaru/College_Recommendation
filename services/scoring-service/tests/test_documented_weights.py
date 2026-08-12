"""The rubric shares quoted in prose must be the shares the code applies.

`docs/contracts/score.schema.json` said culture "drives 20% of the score" while
`DEFAULT_WEIGHTS["culture"]` had been 0.18 since v3.0.0, and a test docstring
called academic "the heaviest weight (0.35)" when it is 0.28. Nobody reading
either would have doubted it - which is the whole problem with a number typed
into a sentence. This test is the reason to keep quoting them: it fails when
they drift again.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from app.scoring import DEFAULT_WEIGHTS

CONTRACTS = Path(__file__).resolve().parents[3] / "docs" / "contracts"


def _share(dimension: str) -> int:
    """The dimension's weight as the whole-number percentage prose would use."""
    return round(DEFAULT_WEIGHTS[dimension] * 100)


def test_the_default_weights_are_a_whole_rubric():
    """Every "N% of the score" claim depends on the weights summing to 1.0."""
    assert round(sum(DEFAULT_WEIGHTS.values()), 6) == 1.0


def test_the_contract_quotes_the_real_culture_share():
    schema = json.loads((CONTRACTS / "score.schema.json").read_text(encoding="utf-8"))
    description = schema["$defs"]["University"]["properties"]["culture"]["description"]

    quoted = re.search(r"(\d+)% of the score", description)

    assert quoted, f"no share quoted in: {description}"
    assert int(quoted.group(1)) == _share("culture")


@pytest.mark.parametrize("path", sorted(CONTRACTS.glob("*.schema.json")))
def test_no_contract_quotes_a_share_that_no_dimension_has(path: Path):
    """Catches the same drift anywhere else in the contracts, including fields
    that gain a share claim later."""
    shares = {_share(dimension) for dimension in DEFAULT_WEIGHTS}

    for quoted in re.findall(r"(\d+)% of the (?:score|rubric)", path.read_text(encoding="utf-8")):
        assert int(quoted) in shares, f"{path.name} quotes {quoted}%, which no dimension carries"


def test_academic_is_still_the_heaviest_dimension():
    """The academic_fit regression docstring rests on this being true."""
    assert max(DEFAULT_WEIGHTS, key=lambda k: DEFAULT_WEIGHTS[k]) == "academic"
