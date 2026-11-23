"""Rising, steady or falling: the trend from the readings of the last hour."""
from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from custom_components.swiss_waters.trend import FALLING, RISING, STEADY, Trends, classify, station_trend

START = datetime(2026, 11, 23, 12, 0, tzinfo=UTC)


def _reading(minutes: int, **values) -> dict:
    return {"2135": {"measurement_time": (START + timedelta(minutes=minutes)).isoformat(), "fresh": True, **values}}


def _feed(trends: Trends, series: list[tuple[int, dict]]) -> dict:
    stations = {}
    for minutes, values in series:
        stations = _reading(minutes, **values)
        trends.update(stations)
    return stations["2135"]


@pytest.mark.parametrize(("measure", "change", "value", "expected"), [
    ("water_level", 0.02, 500.0, RISING),
    ("water_level", 0.019, 500.0, STEADY),
    ("water_level", -0.05, 500.0, FALLING),
    ("temperature", 0.3, 10.0, RISING),
    ("temperature", -0.29, 10.0, STEADY),
    ("discharge", 5.0, 100.0, RISING),  # 5 % of the flow
    ("discharge", 4.9, 100.0, STEADY),
    ("discharge", -70.0, 1400.0, FALLING),
    ("discharge", 0.04, 0.1, STEADY),  # a brook near zero: the floor of 0.05
    ("discharge", 2.0, -39.0, RISING),  # a negative flow counts by its size
])
def test_classify(measure, change, value, expected):
    assert classify(measure, change, value) == expected


def test_no_trend_before_half_an_hour_of_readings():
    trends = Trends()
    station = _feed(trends, [(0, {"water_level": 500.00}), (10, {"water_level": 500.05}), (20, {"water_level": 500.10})])
    assert station["trends"] == {}
    assert station_trend(station) == (None, None)
    station = _feed(trends, [(30, {"water_level": 500.15})])
    assert station["trends"]["water_level"] == {"trend": RISING, "change_per_hour": 0.3}
    assert station_trend(station) == (RISING, "water_level")


def test_the_newest_reading_is_compared_with_the_one_an_hour_before():
    trends = Trends()
    # a rise two hours ago, level since then
    series = [(m, {"water_level": 500.0 + (0.5 if m >= 30 else 0.0)}) for m in range(0, 160, 10)]
    station = _feed(trends, series)
    assert station["trends"]["water_level"] == {"trend": STEADY, "change_per_hour": 0.0}


def test_each_measure_has_its_own_trend_and_the_level_leads():
    trends = Trends()
    station = _feed(trends, [
        (0, {"water_level": 500.0, "discharge": 100.0, "temperature": 10.0}),
        (60, {"water_level": 499.9, "discharge": 120.0, "temperature": 10.1}),
    ])
    assert station["trends"]["water_level"]["trend"] == FALLING
    assert station["trends"]["discharge"] == {"trend": RISING, "change_per_hour": 20.0}
    assert station["trends"]["temperature"]["trend"] == STEADY
    assert station_trend(station) == (FALLING, "water_level")
    # a station without a level is judged by its discharge
    assert station_trend({"trends": {"discharge": {"trend": RISING}}}) == (RISING, "discharge")
    assert station_trend({"trends": {"temperature": {"trend": RISING}}}) == (None, None)
    assert station_trend({}) == (None, None)


def test_a_repeated_reading_is_taken_once_and_old_ones_are_dropped():
    trends = Trends()
    _feed(trends, [(0, {"water_level": 500.0}), (0, {"water_level": 500.0}), (0, {"water_level": 500.0})])
    assert len(trends._history[("2135", "water_level")]) == 1
    _feed(trends, [(m, {"water_level": 500.0}) for m in range(10, 400, 10)])
    history = trends._history[("2135", "water_level")]
    assert history[-1][0] - history[0][0] <= timedelta(hours=3)


def test_stale_missing_and_unreadable_readings_have_no_trend():
    trends = Trends()
    _feed(trends, [(0, {"water_level": 500.0})])
    stale = {"2135": {"measurement_time": (START + timedelta(minutes=60)).isoformat(), "fresh": False, "water_level": 501.0}}
    trends.update(stale)
    assert stale["2135"]["trends"] == {}
    for broken in ({"measurement_time": None, "fresh": True, "water_level": 1.0}, {"measurement_time": "yesterday", "fresh": True, "water_level": 1.0},
                   {"measurement_time": (START + timedelta(minutes=60)).isoformat(), "fresh": True, "water_level": None}):
        stations = {"2135": broken}
        trends.update(stations)
        assert stations["2135"]["trends"] == {}


def test_naive_times_are_read_as_utc_and_gone_stations_are_forgotten():
    trends = Trends()
    trends.update({"2135": {"measurement_time": "2026-11-23T12:00:00", "fresh": True, "water_level": 500.0}})
    stations = {"2135": {"measurement_time": "2026-11-23T13:00:00+00:00", "fresh": True, "water_level": 500.1}}
    trends.update(stations)
    assert stations["2135"]["trends"]["water_level"]["trend"] == RISING
    trends.update({"2029": {"measurement_time": "2026-11-23T13:00:00+00:00", "fresh": True, "water_level": 245.0}})
    assert ("2135", "water_level") not in trends._history
