"""Bathing water classification after the Bathing Water Directive, Annex II."""
from __future__ import annotations

from custom_components.swiss_waters.bathing import _percentile_lognormal, classify


def test_percentile_of_identical_values_is_the_value():
    assert round(_percentile_lognormal([100.0, 100.0, 100.0], 95), 3) == 100.0


def test_single_sample_has_no_spread():
    assert round(_percentile_lognormal([250.0], 90), 3) == 250.0


def test_low_counts_are_excellent():
    samples = {"E.coli": [10.0, 15.0, 20.0, 12.0], "Enterokokken": [5.0, 8.0, 6.0, 4.0]}
    assert classify(samples) == "excellent"


def test_high_counts_are_poor():
    samples = {"E.coli": [2000.0, 3500.0, 1800.0, 4000.0], "Enterokokken": [900.0, 1200.0, 700.0, 1500.0]}
    assert classify(samples) == "poor"


def test_one_parameter_is_enough_and_an_empty_season_has_no_class():
    assert classify({"E.coli": [50.0, 60.0, 40.0]}) == "excellent"
    assert classify({"E.coli": [], "Enterokokken": []}) is None
    assert classify({}) is None


def test_the_worse_parameter_decides():
    samples = {"E.coli": [10.0, 15.0, 20.0], "Enterokokken": [900.0, 1200.0, 700.0]}
    assert classify(samples) == "poor"
