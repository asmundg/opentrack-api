"""Tests for the post-condition poller used by queued OpenTrack tasks."""

import pytest

from opentrack_admin.browser import poll_until


def test_returns_once_the_post_condition_holds():
    calls = []

    def ready() -> bool:
        calls.append(1)
        return len(calls) == 3

    poll_until(ready, timeout=10.0, description="test", interval=0)
    assert len(calls) == 3


def test_raises_when_the_post_condition_never_holds():
    with pytest.raises(TimeoutError, match="test"):
        poll_until(lambda: False, timeout=0.05, description="test", interval=0.01)
