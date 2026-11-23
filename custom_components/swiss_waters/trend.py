"""Trend of a station's readings: rising, steady or falling.

The FOEN feed carries only the latest reading of a station. The integration
keeps the readings it has seen for a few hours and compares the newest one
with the reading of about an hour before. Nothing is fetched for this, and
nothing is stored: after a restart a trend is back once half an hour of
readings has come in.
"""
from __future__ import annotations

from datetime import UTC, datetime, timedelta

from homeassistant.util import dt as dt_util

RISING = "rising"
STEADY = "steady"
FALLING = "falling"
TRENDS = [RISING, STEADY, FALLING]

MEASURES = ("water_level", "discharge", "temperature")

# The newest reading is compared with the oldest one of the last hour ...
WINDOW = timedelta(minutes=60)
# ... once the two lie at least this far apart,
MIN_SPAN = timedelta(minutes=30)
# and readings older than this are dropped.
KEEP = timedelta(hours=3)

# A change per hour below these counts as steady. Water level: 2 cm an hour.
# Temperature: 0.3 °C an hour. Discharge: 5 % of the flow an hour, at least
# 0.05 m³/s so that a brook near zero does not flip on noise.
LEVEL_STEP = 0.02
TEMPERATURE_STEP = 0.3
DISCHARGE_SHARE = 0.05
DISCHARGE_FLOOR = 0.05


def _parse(timestamp: str | None) -> datetime | None:
    measured = dt_util.parse_datetime(timestamp) if timestamp else None
    if measured is None:
        return None
    return measured if measured.tzinfo else measured.replace(tzinfo=UTC)


def classify(measure: str, change_per_hour: float, value: float) -> str:
    """Rising, steady or falling for a change per hour of a measure."""
    if measure == "water_level":
        step = LEVEL_STEP
    elif measure == "temperature":
        step = TEMPERATURE_STEP
    else:
        step = max(abs(value) * DISCHARGE_SHARE, DISCHARGE_FLOOR)
    if change_per_hour >= step:
        return RISING
    if change_per_hour <= -step:
        return FALLING
    return STEADY


class Trends:
    """The recent readings of the stations of one entry."""

    def __init__(self) -> None:
        self._history: dict[tuple[str, str], list[tuple[datetime, float]]] = {}

    def update(self, stations: dict[str, dict]) -> None:
        """Take in the latest readings and set every station's ``trends``:
        {measure: {"trend": ..., "change_per_hour": ...}} for the measures
        that have enough history. A stale reading has no trend."""
        for station_id, station in stations.items():
            measured = _parse(station.get("measurement_time"))
            trends: dict[str, dict] = {}
            for measure in MEASURES:
                value = station.get(measure)
                if measured is None or value is None or not station.get("fresh"):
                    continue
                history = self._history.setdefault((station_id, measure), [])
                if not history or measured > history[-1][0]:
                    history.append((measured, float(value)))
                while history and measured - history[0][0] > KEEP:
                    history.pop(0)
                change = self._change_per_hour(history)
                if change is not None:
                    trends[measure] = {"trend": classify(measure, change, float(value)), "change_per_hour": round(change, 3)}
            station["trends"] = trends
        # forget stations that left the selection
        for key in [k for k in self._history if k[0] not in stations]:
            del self._history[key]

    @staticmethod
    def _change_per_hour(history: list[tuple[datetime, float]]) -> float | None:
        newest_time, newest = history[-1]
        base = next(((when, value) for when, value in history if newest_time - when <= WINDOW), None)
        if base is None or newest_time - base[0] < MIN_SPAN:
            return None
        hours = (newest_time - base[0]).total_seconds() / 3600
        return (newest - base[1]) / hours


def station_trend(station: dict) -> tuple[str | None, str | None]:
    """The trend that stands for the station and the measure it comes from:
    the water level, else the discharge."""
    trends = station.get("trends") or {}
    for measure in ("water_level", "discharge"):
        if measure in trends:
            return trends[measure]["trend"], measure
    return None, None
