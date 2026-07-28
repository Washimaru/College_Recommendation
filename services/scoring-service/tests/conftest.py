import pytest

from app.schemas import Profile, University


@pytest.fixture
def profile() -> Profile:
    return Profile(
        gpa=3.8,
        sat=1400,
        mbti="ENFP",
        intended_major="Computer Science",
        preferences={"max_tuition": 40000, "preferred_size": "large", "locations": ["CA"]},
    )


@pytest.fixture
def universities() -> list[University]:
    return [
        University(id="u1", name="Alpha U", avg_gpa=3.9, avg_sat=1450, acceptance_rate=0.15,
                   tuition=38000, size="large", location="CA", majors=["Computer Science", "Math"]),
        University(id="u2", name="Beta College", avg_gpa=3.5, avg_sat=1300, acceptance_rate=0.55,
                   tuition=52000, size="small", location="NY", majors=["Biology"]),
        University(id="u3", name="Gamma Tech", avg_gpa=3.7, avg_sat=1400, acceptance_rate=0.25,
                   tuition=30000, size="large", location="CA", majors=["Computer Science"]),
    ]
