import tomllib
from pathlib import Path

import pytest

from gpx_factory import gpx_from_points, straight_line_points
from mountain_software.observations.schema import ObservationError, load_file, parse_observation
from mountain_software.observations.store import store_observations
from mountain_software.routes import load_all

ROOT = Path(__file__).resolve().parents[1]
TEMPLATE = ROOT / "templates/field_observation.toml"


def base(**kw):
    d = {
        "obs_key": "k1",
        "source_type": "own_field",
        "observer": "Tester",
        "observed_at": "2026-12-01T09:30:00-07:00",
        "time_precision": "exact",
        "confidence": "high",
        "sentence": "Nothing seen.",
    }
    d.update(kw)
    return d


def test_template_is_valid():
    obs = load_file(TEMPLATE)
    assert len(obs) == 1
    o = obs[0]
    assert o.observed_at_utc.isoformat() == "2026-12-01T16:30:00+00:00"  # stored in UTC
    assert o.wind_effect == "loaded" and o.evidence[0].kind == "quote"


@pytest.mark.parametrize(
    "change,msg",
    [
        ({"observed_at": "2026-12-01T09:30:00"}, "time zone"),
        ({"confidence": "certain"}, "confidence"),
        ({"wind_effect": "blown"}, "wind_effect"),
        ({"transport_signs": ["snowballs"]}, "transport_signs"),
        ({"wind_speed_kmh": -5}, "wind_speed_kmh"),
        ({"sentence": ""}, "sentence"),
        ({"source_type": "other_report"}, "link"),
        ({"published_at": "2026-11-30T09:00:00-07:00"}, "before observed"),
        ({"forecast_issue": "2026-12-01T10:00:00-07:00"}, "forecast_issue"),
    ],
)
def test_bad_entries_rejected(change, msg):
    with pytest.raises(ObservationError, match=msg):
        parse_observation(base(**change))


def test_bare_date_means_day_precision():
    o = parse_observation(base(observed_at=tomllib.loads("d = 2026-10-16")["d"], time_precision="day"))
    assert o.observed_at_utc.isoformat() == "2026-10-16T06:00:00+00:00"  # local midnight MDT


def test_store_links_nearest_route_point_and_replaces(conn, tmp_path):
    (tmp_path / "own").mkdir()
    (tmp_path / "own/a.gpx").write_text(gpx_from_points(straight_line_points(1000, 50, lat0=51.40, lon0=-116.30)))
    (tmp_path / "m.toml").write_text(
        '[[regions]]\nregion_id = "r"\nname = "R"\n[[routes]]\nroute_id = "a"\nname = "A"\nregion_id = "r"\n'
        'route_shape = "one_way"\nfile = "own/a.gpx"\nsource = "s"\ndownload_date = "2026-11-18"\nterms_note = "t"\n'
    )
    load_all(conn, tmp_path / "m.toml")
    near = base(lat=51.4045, lon=-116.3001, evidence=[{"kind": "quote", "text": "x"}])
    far = base(obs_key="k2", lat=51.50, lon=-116.30)
    store_observations(conn, [parse_observation(near), parse_observation(far)])
    rows = {r["obs_key"]: r for r in conn.execute("SELECT * FROM observations")}
    assert rows["k1"]["nearest_route_id"] == "a" and rows["k1"]["nearest_seq"] == 2
    assert rows["k2"]["nearest_route_id"] is None
    store_observations(conn, [parse_observation(near)])
    assert conn.execute("SELECT COUNT(*) FROM observations").fetchone()[0] == 2
    assert conn.execute("SELECT COUNT(*) FROM observation_evidence").fetchone()[0] == 1
