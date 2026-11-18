"""Module 5: field observations, as structured fields plus one plain sentence.

An observation is anything someone saw on the mountain at a known time:
"NE ridge at 3,200 m, fresh cornices on the east side, wind about 30 km/h
from the west". The fields make it searchable; the sentence keeps the
meaning a person wrote.

Two dates are always kept apart: when it was SEEN (``observed_at_utc``) and
when it was WRITTEN or PUBLISHED (``published_at_utc``). Mixing them up is
look-ahead bias in disguise.

Negative observations ("stable, nothing seen") count. Logging only
dramatic things would teach the model that every day is dramatic
(selection bias).
"""

from __future__ import annotations

import tomllib
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

SOURCE_TYPES = ("own_field", "own_trip_report", "min_report", "other_report", "photo", "satellite")
CONFIDENCE = ("high", "medium", "low")
TIME_PRECISION = ("exact", "hour", "part_of_day", "day")
WIND_METHODS = ("measured", "estimated")
WIND_KINDS = ("sustained", "gust")
WIND_EFFECTS = ("loaded", "scoured", "mixed", "none_seen", "unknown")
TRANSPORT_SIGNS = ("plumes", "cornices", "scoured", "loaded", "sastrugi", "pillows", "drifts", "none")
SURFACE_TYPES = (
    "powder", "wind_slab", "wind_crust", "sun_crust", "melt_freeze_crust", "corn", "wet", "ice",
    "rock", "scree", "firm", "mixed", "unknown",
)
LANDFORMS = ("ridge", "couloir_gully", "basin_valley", "steep_face", "open_slope", "glacier", "summit", "col", "unknown")


class ObservationError(ValueError):
    pass


@dataclass
class Evidence:
    kind: str  # 'quote', 'link', 'photo'
    text: str | None = None
    url: str | None = None
    author: str | None = None
    published: str | None = None
    note: str | None = None


@dataclass
class Observation:
    obs_key: str
    source_type: str
    observer: str
    observed_at_utc: datetime
    time_precision: str
    confidence: str
    sentence: str
    published_at_utc: datetime | None = None
    peak_id: str | None = None
    route_id: str | None = None
    lat: float | None = None
    lon: float | None = None
    elev_m: float | None = None
    location_note: str | None = None
    landform: str = "unknown"
    aspect_deg: float | None = None
    forecast_source: str | None = None
    forecast_issue_utc: datetime | None = None
    wind_speed_kmh: float | None = None
    wind_from_deg: float | None = None
    wind_method: str | None = None
    wind_kind: str | None = None
    air_temp_c: float | None = None
    precip_type: str | None = None
    surface_type: str = "unknown"
    penetration_cm: float | None = None
    penetration_mode: str | None = None
    new_snow_cm: float | None = None
    transport_signs: list[str] = field(default_factory=list)
    wind_effect: str = "unknown"
    avalanche_seen: bool | None = None
    avalanche_aspect_deg: float | None = None
    avalanche_elev_m: float | None = None
    avalanche_size: float | None = None
    avalanche_type: str | None = None
    avalanche_age: str | None = None
    avalanche_trigger: str | None = None
    bergschrund: str | None = None
    bridge_quality: str | None = None
    cloud: str | None = None
    visibility: str | None = None
    photo_files: list[str] = field(default_factory=list)
    is_negative: bool = False
    needs_review: bool = False
    evidence: list[Evidence] = field(default_factory=list)


def _dt(value: Any, name: str) -> datetime | None:
    """Accept a TOML datetime/date or ISO text; require a time zone for datetimes."""
    if value is None:
        return None
    if isinstance(value, datetime):
        dt = value
    elif isinstance(value, date):
        dt = datetime(value.year, value.month, value.day)
        return dt.replace(tzinfo=UTC)  # a bare date: day precision, stored as 00:00 UTC
    else:
        try:
            dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        except ValueError as exc:
            raise ObservationError(f"{name}: unreadable time {value!r}") from exc
    if dt.tzinfo is None:
        raise ObservationError(f"{name}: time {value!r} has no time zone; write e.g. 2026-10-16T09:30:00-06:00")
    return dt.astimezone(UTC)


def _choice(value: Any, allowed: tuple[str, ...], name: str, optional: bool = True) -> str | None:
    if value is None and optional:
        return None
    if value not in allowed:
        raise ObservationError(f"{name}: {value!r} is not one of {', '.join(allowed)}")
    return value


def _num(value: Any, name: str, lo: float | None = None, hi: float | None = None) -> float | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ObservationError(f"{name}: expected a number, got {value!r}")
    v = float(value)
    if (lo is not None and v < lo) or (hi is not None and v > hi):
        raise ObservationError(f"{name}: {v} is outside {lo}..{hi}")
    return v


def parse_observation(d: dict[str, Any]) -> Observation:
    """Check one observation entry (a TOML table) and return an Observation."""
    for req in ("obs_key", "source_type", "observer", "observed_at", "time_precision", "confidence", "sentence"):
        if d.get(req) in (None, ""):
            raise ObservationError(f"missing required field '{req}'")
    signs = list(d.get("transport_signs", []))
    for s in signs:
        _choice(s, TRANSPORT_SIGNS, "transport_signs")
    ev = []
    for e in d.get("evidence", []):
        if e.get("kind") not in ("quote", "link", "photo"):
            raise ObservationError(f"evidence kind {e.get('kind')!r} must be quote, link or photo")
        if e["kind"] == "quote" and not e.get("text"):
            raise ObservationError("quote evidence needs the exact text")
        ev.append(Evidence(**{k: e.get(k) for k in ("kind", "text", "url", "author", "published", "note")}))
    obs = Observation(
        obs_key=str(d["obs_key"]),
        source_type=_choice(d["source_type"], SOURCE_TYPES, "source_type", optional=False),
        observer=str(d["observer"]),
        observed_at_utc=_dt(d["observed_at"], "observed_at"),
        time_precision=_choice(d["time_precision"], TIME_PRECISION, "time_precision", optional=False),
        confidence=_choice(d["confidence"], CONFIDENCE, "confidence", optional=False),
        sentence=str(d["sentence"]).strip(),
        published_at_utc=_dt(d.get("published_at"), "published_at"),
        peak_id=d.get("peak_id"),
        route_id=d.get("route_id"),
        lat=_num(d.get("lat"), "lat", -90, 90),
        lon=_num(d.get("lon"), "lon", -180, 180),
        elev_m=_num(d.get("elev_m"), "elev_m", 0, 5000),
        location_note=d.get("location_note"),
        landform=_choice(d.get("landform", "unknown"), LANDFORMS, "landform", optional=False),
        aspect_deg=_num(d.get("aspect_deg"), "aspect_deg", 0, 360),
        forecast_source=d.get("forecast_source"),
        forecast_issue_utc=_dt(d.get("forecast_issue"), "forecast_issue"),
        wind_speed_kmh=_num(d.get("wind_speed_kmh"), "wind_speed_kmh", 0, 250),
        wind_from_deg=_num(d.get("wind_from_deg"), "wind_from_deg", 0, 360),
        wind_method=_choice(d.get("wind_method"), WIND_METHODS, "wind_method"),
        wind_kind=_choice(d.get("wind_kind"), WIND_KINDS, "wind_kind"),
        air_temp_c=_num(d.get("air_temp_c"), "air_temp_c", -60, 40),
        precip_type=d.get("precip_type"),
        surface_type=_choice(d.get("surface_type", "unknown"), SURFACE_TYPES, "surface_type", optional=False),
        penetration_cm=_num(d.get("penetration_cm"), "penetration_cm", 0, 300),
        penetration_mode=_choice(d.get("penetration_mode"), ("boot", "ski"), "penetration_mode"),
        new_snow_cm=_num(d.get("new_snow_cm"), "new_snow_cm", 0, 500),
        transport_signs=signs,
        wind_effect=_choice(d.get("wind_effect", "unknown"), WIND_EFFECTS, "wind_effect", optional=False),
        avalanche_seen=d.get("avalanche_seen"),
        avalanche_aspect_deg=_num(d.get("avalanche_aspect_deg"), "avalanche_aspect_deg", 0, 360),
        avalanche_elev_m=_num(d.get("avalanche_elev_m"), "avalanche_elev_m", 0, 5000),
        avalanche_size=_num(d.get("avalanche_size"), "avalanche_size", 1, 5),
        avalanche_type=d.get("avalanche_type"),
        avalanche_age=d.get("avalanche_age"),
        avalanche_trigger=d.get("avalanche_trigger"),
        bergschrund=d.get("bergschrund"),
        bridge_quality=d.get("bridge_quality"),
        cloud=d.get("cloud"),
        visibility=d.get("visibility"),
        photo_files=list(d.get("photo_files", [])),
        is_negative=bool(d.get("is_negative", False)),
        needs_review=bool(d.get("needs_review", False)),
        evidence=ev,
    )
    if obs.published_at_utc and obs.published_at_utc < obs.observed_at_utc and obs.time_precision == "exact":
        raise ObservationError("published_at is before observed_at")
    if obs.source_type in ("other_report", "min_report") and not any(e.url for e in obs.evidence):
        raise ObservationError("someone else's report needs a link in evidence (store the link, not a copy)")
    return obs


def load_file(path: Path) -> list[Observation]:
    """Read every [[observations]] entry in a TOML file."""
    with open(path, "rb") as fh:
        data = tomllib.load(fh)
    entries = data.get("observations", [])
    keys = [e.get("obs_key") for e in entries]
    if len(keys) != len(set(keys)):
        raise ObservationError(f"{path}: duplicate obs_key")
    out = []
    for i, e in enumerate(entries):
        try:
            out.append(parse_observation(e))
        except ObservationError as exc:
            raise ObservationError(f"{path} entry {i + 1} ({e.get('obs_key')}): {exc}") from exc
    return out
