from datetime import datetime, timedelta, timezone

import pytest

from whistler_traffic.timeutil import VANCOUVER, key_timestamp


def test_key_timestamp_converts_to_utc():
    dt = datetime(2026, 11, 25, 15, 4, 12, tzinfo=timezone(timedelta(hours=-8)))
    assert key_timestamp(dt) == "20261125T230412Z"


def test_tzdata_has_bc_permanent_utc_minus_7():
    """Fails on machines with tzdata older than BC's Nov 2026 switch (fix: upgrade tzdata)."""
    dt = datetime(2027, 1, 15, 12, tzinfo=VANCOUVER)
    assert dt.utcoffset() == timedelta(hours=-7)


def test_naive_datetime_rejected():
    with pytest.raises(ValueError):
        key_timestamp(datetime(2026, 11, 25))  # noqa: DTZ001
