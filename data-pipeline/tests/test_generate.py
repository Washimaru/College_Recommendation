from generate import MAJOR_POOL, SIZES, generate_universities, main


def test_count_and_ids():
    unis = generate_universities(50, seed=1)
    assert len(unis) == 50
    ids = [u["id"] for u in unis]
    assert len(set(ids)) == 50  # unique
    assert ids[0] == "u0000"


def test_deterministic_for_seed():
    assert generate_universities(30, seed=7) == generate_universities(30, seed=7)


def test_different_seeds_differ():
    assert generate_universities(30, seed=1) != generate_universities(30, seed=2)


def test_fields_in_realistic_ranges():
    for u in generate_universities(200, seed=3):
        assert 0.0 <= u["acceptance_rate"] <= 1.0
        assert 900 <= u["avg_sat"] <= 1580
        assert 2.0 <= u["avg_gpa"] <= 4.0
        assert 8000 <= u["tuition"] <= 65000
        assert u["size"] in SIZES
        assert 2 <= len(u["majors"]) <= 4
        assert set(u["majors"]).issubset(set(MAJOR_POOL))
        assert u["majors"] == sorted(u["majors"])


def test_selectivity_correlates_with_scores():
    unis = generate_universities(300, seed=9)
    selective = [u for u in unis if u["acceptance_rate"] < 0.2]
    open_adm = [u for u in unis if u["acceptance_rate"] > 0.7]
    avg = lambda xs: sum(xs) / len(xs)  # noqa: E731
    assert avg([u["avg_sat"] for u in selective]) > avg([u["avg_sat"] for u in open_adm])


def test_unique_names():
    unis = generate_universities(150, seed=5)
    names = [u["name"] for u in unis]
    assert len(set(names)) == len(names)


def test_main_writes_file(tmp_path, capsys):
    out = tmp_path / "unis.json"
    rc = main(["--count", "5", "--seed", "2", "--out", str(out)])
    assert rc == 0
    import json
    rows = json.loads(out.read_text())
    assert len(rows) == 5


def test_main_stdout(capsys):
    rc = main(["--count", "3", "--seed", "2", "--out", "-"])
    assert rc == 0
    out = capsys.readouterr().out
    import json
    assert len(json.loads(out)) == 3
