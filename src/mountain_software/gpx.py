"""Read GPX files and tidy their points.

GPX is the XML format watches and mapping sites use for tracks. A file holds
track points (``<trkpt>``), sometimes route points (``<rtept>``) and named
waypoints (``<wpt>``). We only use the standard library XML parser so every
line is readable without learning a GPX package.

Elevation read from a GPX file is called ``ele_gpx_m`` everywhere. It comes
from the watch barometer or GPS, or from whatever the website added. It is
NOT terrain truth: terrain elevation comes from a DEM in a later module.
"""

from __future__ import annotations

import hashlib
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

METHOD_VERSION = "gpx-load-v1"


@dataclass(frozen=True)
class TrackPoint:
    lat: float
    lon: float
    ele_gpx_m: float | None = None
    time_utc: datetime | None = None


@dataclass(frozen=True)
class Waypoint:
    lat: float
    lon: float
    name: str | None = None


@dataclass
class GpxTrack:
    points: list[TrackPoint]
    waypoints: list[Waypoint] = field(default_factory=list)
    name: str | None = None
    creator: str | None = None
    copyright_author: str | None = None
    licence: str | None = None

    @property
    def is_timed(self) -> bool:
        """True when at least half the points carry a timestamp."""
        if not self.points:
            return False
        timed = sum(1 for p in self.points if p.time_utc is not None)
        return timed >= len(self.points) / 2


class GpxError(ValueError):
    """The file is not usable GPX."""


def _local(tag: str) -> str:
    """Strip the XML namespace: '{http://www.topografix.com/GPX/1/1}trkpt' -> 'trkpt'."""
    return tag.rsplit("}", 1)[-1]


def _child(el: ET.Element, name: str) -> ET.Element | None:
    for c in el:
        if _local(c.tag) == name:
            return c
    return None


def _child_text(el: ET.Element, name: str) -> str | None:
    c = _child(el, name)
    if c is None or c.text is None:
        return None
    text = c.text.strip()
    return text or None


def parse_time_utc(text: str) -> datetime:
    """Parse a GPX timestamp and return it in UTC.

    GPX times are ISO 8601, usually ending in 'Z' (UTC). A time with no zone
    at all is ambiguous; the GPX standard says times are UTC, so we follow it.
    """
    t = text.strip()
    if t.endswith("Z"):
        t = t[:-1] + "+00:00"
    dt = datetime.fromisoformat(t)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC)


def _parse_point(el: ET.Element) -> TrackPoint | None:
    try:
        lat = float(el.attrib["lat"])
        lon = float(el.attrib["lon"])
    except (KeyError, ValueError):
        return None
    ele_text = _child_text(el, "ele")
    try:
        ele = float(ele_text) if ele_text is not None else None
    except ValueError:
        ele = None
    time_text = _child_text(el, "time")
    try:
        time = parse_time_utc(time_text) if time_text else None
    except ValueError:
        time = None
    return TrackPoint(lat=lat, lon=lon, ele_gpx_m=ele, time_utc=time)


def parse_gpx(source: str | bytes | Path) -> GpxTrack:
    """Parse GPX text, bytes or a file path into a :class:`GpxTrack`.

    All ``<trkpt>`` in every track and segment are joined in file order. If the
    file has no track points, ``<rtept>`` route points are used instead.
    """
    if isinstance(source, Path):
        data: str | bytes = source.read_bytes()
    else:
        data = source
    try:
        root = ET.fromstring(data)
    except ET.ParseError as exc:
        raise GpxError(f"not valid XML: {exc}") from exc
    if _local(root.tag) != "gpx":
        raise GpxError(f"root element is <{_local(root.tag)}>, expected <gpx>")

    trkpts: list[TrackPoint] = []
    rtepts: list[TrackPoint] = []
    waypoints: list[Waypoint] = []
    name = None
    for el in root.iter():
        tag = _local(el.tag)
        if tag == "trkpt":
            p = _parse_point(el)
            if p:
                trkpts.append(p)
        elif tag == "rtept":
            p = _parse_point(el)
            if p:
                rtepts.append(p)
        elif tag == "wpt":
            p = _parse_point(el)
            if p:
                waypoints.append(Waypoint(p.lat, p.lon, _child_text(el, "name")))
        elif tag == "trk" and name is None:
            name = _child_text(el, "name")

    copyright_author = None
    licence = None
    meta = _child(root, "metadata")
    if meta is not None:
        if name is None:
            name = _child_text(meta, "name")
        cr = _child(meta, "copyright")
        if cr is not None:
            copyright_author = cr.attrib.get("author")
            licence = _child_text(cr, "license")

    points = trkpts or rtepts
    if not points:
        raise GpxError("no track or route points found")
    return GpxTrack(
        points=points,
        waypoints=waypoints,
        name=name,
        creator=root.attrib.get("creator"),
        copyright_author=copyright_author,
        licence=licence,
    )


def file_sha256(path: Path) -> str:
    """Fingerprint of a file, so we can tell later if it was swapped or edited."""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def valid_coordinate(p: TrackPoint) -> bool:
    return -90.0 <= p.lat <= 90.0 and -180.0 <= p.lon <= 180.0 and not (p.lat == 0.0 and p.lon == 0.0)


def clean_points(points: list[TrackPoint]) -> list[TrackPoint]:
    """Drop impossible coordinates and back-to-back repeats of the same spot.

    A watch that is paused often writes the same position many times. Those
    repeats add no distance, but they inflate the point count and confuse
    time thinning, so we keep only the first of each run.
    """
    out: list[TrackPoint] = []
    for p in points:
        if not valid_coordinate(p):
            continue
        if out and out[-1].lat == p.lat and out[-1].lon == p.lon:
            continue
        out.append(p)
    return out


def median_interval_s(points: list[TrackPoint]) -> float | None:
    """Typical seconds between consecutive timed points (None if untimed)."""
    gaps = [
        (b.time_utc - a.time_utc).total_seconds()
        for a, b in zip(points, points[1:])
        if a.time_utc is not None and b.time_utc is not None
    ]
    gaps = [g for g in gaps if g > 0]
    if not gaps:
        return None
    gaps.sort()
    mid = len(gaps) // 2
    return gaps[mid] if len(gaps) % 2 else (gaps[mid - 1] + gaps[mid]) / 2


def thin_by_time(points: list[TrackPoint], min_interval_s: float = 10.0) -> list[TrackPoint]:
    """Keep about one point every ``min_interval_s`` seconds.

    Why: a 1 Hz watch track records a point every second. Each fix wobbles a
    few metres, and at walking pace the wobble is as big as the real step, so
    adding up 1-second steps measures the wobble too (33.0 km instead of about
    25 km on North Victoria). Keeping one point per ~10 s lets real movement
    dominate the wobble.

    Rule: always keep the first point; keep a later point when at least
    ``min_interval_s`` has passed since the last kept point; always keep the
    last point. Points without a time are kept unchanged (nothing to thin by).
    """
    if not points:
        return []
    kept = [points[0]]
    last_time = points[0].time_utc
    for p in points[1:-1]:
        if p.time_utc is None or last_time is None:
            kept.append(p)
            last_time = p.time_utc
            continue
        if (p.time_utc - last_time).total_seconds() >= min_interval_s:
            kept.append(p)
            last_time = p.time_utc
    if len(points) > 1:
        kept.append(points[-1])
    return kept
