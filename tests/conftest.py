"""Shared notes for the Swiss Waters tests.

Tests that need a Home Assistant instance request `hass` and
`enable_custom_integrations`; the `source` fixture fakes the FOEN station
feed and the `bathing` fixture the bathing sources for a whole test.
"""
from __future__ import annotations

import pytest

from .common import Bathing, Source


@pytest.fixture
def source(enable_custom_integrations):
    fake = Source()
    with fake.patch():
        yield fake


@pytest.fixture
def bathing(enable_custom_integrations):
    fake = Bathing()
    a, b, c, d = fake.patches()
    with a, b, c, d:
        yield fake
