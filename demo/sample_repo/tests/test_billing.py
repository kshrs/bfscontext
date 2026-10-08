"""
Tests for billing service.
"""

from billing import charge_user, validate_charge_amount


def test_validate_charge_amount():
    assert validate_charge_amount(50.0) is True
    assert validate_charge_amount(-10.0) is False
