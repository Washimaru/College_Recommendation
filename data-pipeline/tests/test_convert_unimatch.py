"""Tier-1 converter: parse the UniMatch editorial dataset out of its JS files.

The source is JavaScript, not JSON: keys are unquoted and floats may be written
with a leading dot (`collab:.7`). Tests use inline fixtures so they never touch
the original project directory.
"""
from __future__ import annotations

import json

from convert_unimatch import convert, parse_universities

ONE_RECORD = """(function (root) {
  const UNIS = [
    {n:"Test Tech",loc:"Cambridge, MA",ctry:"USA",region:"Northeast",type:"Private",size:4600,setting:"urban",net:25000,gpa:3.95,
     strengths:["Engineering","Computer Science"],v:{collab:.7,quirky:.85,idealist:.55,research:.75,spirit:.35,seminar:.55}},
  ];
})(window);"""


def test_parses_core_fields_of_a_single_record():
    unis = parse_universities(ONE_RECORD)

    assert len(unis) == 1
    u = unis[0]
    assert u["name"] == "Test Tech"
    assert u["location"] == "Cambridge, MA"
    assert u["country"] == "USA"
    assert u["region"] == "Northeast"
    assert u["type"] == "Private"
    assert u["enrollment_editorial"] == 4600
    assert u["setting"] == "urban"
    assert u["net_price"] == 25000
    assert u["avg_gpa"] == 3.95
    assert u["majors"] == ["Engineering", "Computer Science"]


TWO_RECORDS = """const UNIS = [
  {n:"Alpha College",loc:"Boston, MA",ctry:"USA",region:"Northeast",type:"Private",size:2000,setting:"urban",net:30000,gpa:3.5,
   strengths:["Biology"],v:{collab:.5,quirky:.5,idealist:.5,research:.5,spirit:.5,seminar:.5}},
  {n:"Beta University",loc:"Austin, TX",ctry:"USA",region:"South",type:"Public",size:40000,setting:"urban",net:20000,gpa:3.6,
   strengths:["Engineering"],v:{collab:.4,quirky:.3,idealist:.6,research:.7,spirit:.9,seminar:.2}},
];"""


def test_region_field_does_not_create_phantom_records():
    """`region:"Northeast"` ends in `n:"`. A record matcher that keys on `n:"`
    without requiring the opening brace doubles the record count."""
    unis = parse_universities(TWO_RECORDS)

    assert [u["name"] for u in unis] == ["Alpha College", "Beta University"]


def test_parses_culture_vector_with_leading_dot_floats():
    """`collab:.7` is valid JS but not valid JSON."""
    u = parse_universities(ONE_RECORD)[0]

    assert u["culture"] == {
        "collab": 0.7,
        "quirky": 0.85,
        "idealist": 0.55,
        "research": 0.75,
        "spirit": 0.35,
        "seminar": 0.55,
    }


def test_convert_reads_every_data_file_in_the_directory(tmp_path):
    (tmp_path / "data.js").write_text(ONE_RECORD)
    (tmp_path / "data2.js").write_text(TWO_RECORDS)

    unis = convert(tmp_path)

    assert [u["name"] for u in unis] == ["Test Tech", "Alpha College", "Beta University"]


def test_convert_assigns_unique_slug_ids(tmp_path):
    (tmp_path / "data.js").write_text(TWO_RECORDS)

    unis = convert(tmp_path)

    assert [u["id"] for u in unis] == ["alpha-college", "beta-university"]


def test_write_catalog_emits_deterministic_json(tmp_path):
    """Byte-identical output across runs; ordering stable by id."""
    from convert_unimatch import write_catalog

    (tmp_path / "data.js").write_text(TWO_RECORDS)
    unis = convert(tmp_path)
    out = tmp_path / "unimatch.json"

    write_catalog(unis, out)
    first = out.read_bytes()
    write_catalog(convert(tmp_path), out)

    assert out.read_bytes() == first
    assert json.loads(first)[0]["id"] == "alpha-college"
