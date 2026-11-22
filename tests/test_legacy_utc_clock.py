"""Characterize legacy naive UTC and wire-format compatibility, without writes."""

from datetime import datetime
from datetime import timezone

from bson import BSON

from editor.utils.knowledge_graph_sync import utc_timestamp
from mathmongo.time import naive_utc_now


def test_legacy_clock_matches_aware_utc_and_survives_bson_roundtrip():
    """Legacy date comparisons remain naive; UTC is never local wall time."""
    before = datetime.now(timezone.utc).replace(tzinfo=None)
    actual = naive_utc_now()
    after = datetime.now(timezone.utc).replace(tzinfo=None)
    assert before <= actual <= after
    assert actual.tzinfo is None
    restored = BSON(BSON.encode({'at': actual})).decode()['at']
    assert restored.tzinfo is None
    assert 0 <= (actual - restored).total_seconds() < 0.001


def test_graph_timestamp_keeps_one_z_suffix_and_is_parseable_utc():
    """Existing HTML/JSON consumers retain their ISO UTC representation."""
    stamp = utc_timestamp()
    assert stamp.endswith('Z') and '+00:00' not in stamp
    parsed = datetime.fromisoformat(stamp.replace('Z', '+00:00'))
    assert parsed.utcoffset().total_seconds() == 0
    assert abs((datetime.now(timezone.utc) - parsed).total_seconds()) < 2
