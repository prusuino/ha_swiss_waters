"""Pure helpers of the coordinator: distance, freshness, WKT points and the
merge of SPARQL rows into station records."""
from __future__ import annotations

from datetime import UTC, datetime, timedelta

from custom_components.swiss_waters.coordinator import (
    _parse_bindings,
    _parse_wkt_point,
    haversine_km,
    is_fresh,
)

NOW = datetime(2026, 11, 9, 8, 0, tzinfo=UTC)


def _row(station_id, name, lon, lat, time, **measures):
    binding = {
        "id": {"value": station_id},
        "name": {"value": name},
        "wkt": {"value": f"POINT({lon} {lat})"},
        "water": {"value": "https://ld.admin.ch/dimension/water/Aare"},
        "time": {"value": time},
    }
    for key, value in measures.items():
        binding[key] = {"value": str(value)}
    return binding


def test_haversine_bern_zurich():
    assert round(haversine_km(46.948, 7.447, 47.377, 8.540), 0) == 95


def test_is_fresh():
    assert is_fresh("2026-11-09T07:30:00Z", timedelta(hours=6), NOW) is True
    assert is_fresh("2026-11-09T01:30:00Z", timedelta(hours=6), NOW) is False
    assert is_fresh("2026-11-09T07:30:00", timedelta(hours=6), NOW) is True  # naive = UTC
    assert is_fresh(None, timedelta(hours=6), NOW) is False
    assert is_fresh("yesterday", timedelta(hours=6), NOW) is False


def test_wkt_point():
    assert _parse_wkt_point("POINT(7.447 46.948)") == (46.948, 7.447)
    assert _parse_wkt_point("garbage") is None


def test_bindings_radius_and_favorites_combine():
    rows = [
        _row("2135", "Aare - Bern", 7.447, 46.948, "2026-11-09T07:40:00Z", temperature=9.2, level=502.1),
        _row("2029", "Rhein - Basel", 7.59, 47.56, "2026-11-09T07:40:00Z", discharge=800),
        _row("2473", "Ticino - Bellinzona", 9.02, 46.19, "2026-11-09T07:40:00Z", temperature=12.0),
    ]
    stations = _parse_bindings(rows, 46.948, 7.447, 30.0, favorite_ids={"2473"}, now=NOW)
    assert set(stations) == {"2135", "2473"}  # Basel is 70 km away and no favorite
    bern = stations["2135"]
    assert bern["water_body"] == "Aare"
    assert bern["distance_km"] == 0.0
    assert bern["temperature"] == 9.2 and bern["water_level"] == 502.1 and bern["discharge"] is None
    assert bern["fresh"] is True


def test_bindings_merge_rows_prefer_newest_and_fill_gaps():
    rows = [
        _row("2135", "Aare - Bern", 7.447, 46.948, "2026-11-09T07:00:00Z", temperature=9.0, discharge=120, danger=2),
        _row("2135", "Aare - Bern", 7.447, 46.948, "2026-11-09T07:40:00Z", level=502.3),
    ]
    stations = _parse_bindings(rows, 46.948, 7.447, 10.0, now=NOW)
    bern = stations["2135"]
    assert bern["measurement_time"] == "2026-11-09T07:40:00Z"
    assert bern["water_level"] == 502.3
    assert bern["temperature"] == 9.0 and bern["discharge"] == 120.0 and bern["danger_level"] == 2


def test_bindings_stale_and_broken_rows():
    rows = [
        _row("2135", "Aare - Bern", 7.447, 46.948, "2026-11-08T07:40:00Z", temperature=9.0),
        {"id": {"value": "9999"}, "wkt": {"value": "nowhere"}},
        {"name": {"value": "no id"}},
    ]
    stations = _parse_bindings(rows, 46.948, 7.447, 10.0, now=NOW)
    assert set(stations) == {"2135"}
    assert stations["2135"]["fresh"] is False


def test_radius_zero_keeps_only_favorites():
    rows = [_row("2135", "Aare - Bern", 7.447, 46.948, "2026-11-09T07:40:00Z")]
    assert _parse_bindings(rows, 46.948, 7.447, 0, now=NOW) == {}
    assert set(_parse_bindings(rows, 0, 0, 0, favorite_ids={"2135"}, now=NOW)) == {"2135"}
