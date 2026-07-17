from __future__ import annotations

from pathlib import Path

import pytest


def test_load_fleet_parses_members_and_concurrency(tmp_path):
    from loom.fleet_spec import load_fleet
    (tmp_path / "a.loom.yaml").write_text("x")
    (tmp_path / "b.loom.yaml").write_text("x")
    fp = tmp_path / "fleet.yaml"
    fp.write_text("name: prebeta\nconcurrency: 2\nmembers:\n  - a.loom.yaml\n  - b.loom.yaml\n")
    fs = load_fleet(str(fp))
    assert fs.name == "prebeta"
    assert fs.concurrency == 2
    assert [p.name for p in fs.members] == ["a.loom.yaml", "b.loom.yaml"]
    assert all(p.is_absolute() for p in fs.members)  # resolved relative to fleet dir


def test_load_fleet_defaults_concurrency_4(tmp_path):
    from loom.fleet_spec import load_fleet
    fp = tmp_path / "fleet.yaml"
    fp.write_text("name: f\nmembers:\n  - a.loom.yaml\n")
    assert load_fleet(str(fp)).concurrency == 4


def test_load_fleet_requires_members(tmp_path):
    from loom.fleet_spec import load_fleet
    fp = tmp_path / "fleet.yaml"
    fp.write_text("name: f\nmembers: []\n")
    with pytest.raises(ValueError, match="members"):
        load_fleet(str(fp))
