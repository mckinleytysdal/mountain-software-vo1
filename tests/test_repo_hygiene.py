"""Guards for the public-repo data rules in CLAUDE.md."""

import subprocess
import tomllib
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "data/routes/manifest.toml"


def _git(*args: str) -> str:
    return subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True, check=True).stdout


@pytest.fixture(scope="module")
def tracked_files() -> list[str]:
    try:
        return _git("ls-files").splitlines()
    except (subprocess.CalledProcessError, FileNotFoundError):
        pytest.skip("not a git checkout")


def test_no_third_party_gpx_is_tracked(tracked_files):
    manifest = tomllib.loads(MANIFEST.read_text())
    allowed = {f"data/routes/{r['file']}" for r in manifest["routes"] if r.get("committed_to_repo")}
    tracked_gpx = [f for f in tracked_files if f.lower().endswith(".gpx") and not f.startswith("tests/")]
    assert [f for f in tracked_gpx if f not in allowed] == []
    for r in manifest["routes"]:
        if not r.get("redistribution_allowed"):
            assert not r.get("committed_to_repo"), r["route_id"]


@pytest.mark.parametrize(
    "path",
    [
        "data/routes/third_party/x.gpx",
        "data/routes/local/x.gpx",
        "data/routes/own/x.gpx",
        "data/raw/x.json",
        "data/processed/mountain.sqlite",
    ],
)
def test_gitignore_covers_private_data(path):
    result = subprocess.run(["git", "check-ignore", "-q", path], cwd=ROOT)
    assert result.returncode == 0, f"{path} is not git-ignored"


def test_raw_weather_and_databases_not_tracked(tracked_files):
    assert not [f for f in tracked_files if f.startswith("data/raw/") or f.endswith((".sqlite", ".db"))]
