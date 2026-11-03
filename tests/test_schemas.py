"""Validation tests for security-relevant request schemas."""

import pytest
from pydantic import ValidationError

from satgonetem_gui.schemas import Hping3Request


def test_hping3_accepts_spoofing_fields() -> None:
    """A valid spoofed-source request keeps its network fields."""
    request = Hping3Request(
        src="Gnd0",
        dst="Gnd1",
        proto="tcp",
        sport=1234,
        ttl=5,
        flags=["S"],
        spoof_src="10.0.0.7",
    )

    assert request.spoof_src == "10.0.0.7"
    assert request.sport == 1234
    assert request.ttl == 5


@pytest.mark.parametrize(
    "payload",
    [
        {"flags": ["X"]},
        {"spoof_src": "not-an-ip"},
        {"spoof_src": "2001:db8::1"},
        {"ttl": 0},
        {"sport": 0},
        {"rate_type": "warp"},
        {"proto": "sctp"},
    ],
)
def test_hping3_rejects_invalid_spoofing_fields(payload) -> None:
    """Invalid flags, addresses, and bounds fail validation."""
    with pytest.raises(ValidationError):
        Hping3Request(src="Gnd0", dst="Gnd1", **payload)
