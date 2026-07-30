import pytest

from app.schemas import Culture, Profile, University


def _culture(**overrides) -> Culture:
    base = dict.fromkeys(
        ("collab", "quirky", "idealist", "research", "spirit", "seminar"), 0.5
    )
    return Culture(**{**base, **overrides})


@pytest.fixture
def profile() -> Profile:
    return Profile(
        gpa=3.8,
        sat=1400,
        intended_major="Computer Science",
        culture_prefs={"research": 0.9, "collab": 0.8},
        preferences={"max_tuition": 40000, "preferred_size": "large"},
    )


@pytest.fixture
def universities() -> list[University]:
    return [
        University(id="u1", name="Alpha U", country="USA", avg_gpa=3.9, avg_sat=1450,
                   acceptance_rate=0.15, net_price=38000, size="large", location="CA",
                   region="West", setting="urban", type="Private",
                   majors=["Computer Science", "Math"],
                   culture=_culture(research=0.9, collab=0.8)),
        University(id="u2", name="Beta College", country="USA", avg_gpa=3.5, avg_sat=1300,
                   acceptance_rate=0.55, net_price=52000, size="small", location="NY",
                   region="Northeast", setting="suburban", type="Private",
                   majors=["Biology"], culture=_culture(research=0.2, collab=0.3)),
        University(id="u3", name="Gamma Tech", country="USA", avg_gpa=3.7, avg_sat=1400,
                   acceptance_rate=0.25, net_price=30000, size="large", location="CA",
                   region="West", setting="urban", type="Public",
                   majors=["Computer Science"], culture=_culture(research=0.6, collab=0.5)),
    ]
