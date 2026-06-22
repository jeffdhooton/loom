"""Comprehensive suite for mathlib — the reachable target for the coding loop.

Every assertion here is satisfiable by a correct implementation. Multiple
independent failures appear at once against the buggy seed, so the loop has to
fix several things and re-run pytest across iterations to converge to all-green.
"""

import pytest

from mathlib import add, is_even, factorial, gcd, clamp, mean


def test_add_positive():
    assert add(2, 3) == 5


def test_add_negative():
    assert add(-4, 1) == -3


def test_add_zero():
    assert add(0, 0) == 0


def test_is_even_true():
    assert is_even(4) is True


def test_is_even_false():
    assert is_even(7) is False


def test_is_even_zero():
    assert is_even(0) is True


def test_is_even_negative():
    assert is_even(-3) is False


def test_factorial_zero():
    assert factorial(0) == 1


def test_factorial_one():
    assert factorial(1) == 1


def test_factorial_five():
    assert factorial(5) == 120


def test_factorial_negative_raises():
    with pytest.raises(ValueError):
        factorial(-1)


def test_gcd_basic():
    assert gcd(12, 8) == 4


def test_gcd_coprime():
    assert gcd(7, 1) == 1


def test_gcd_larger():
    assert gcd(54, 24) == 6


def test_clamp_below():
    assert clamp(-5, 0, 10) == 0


def test_clamp_above():
    assert clamp(15, 0, 10) == 10


def test_clamp_within():
    assert clamp(4, 0, 10) == 4


def test_mean_basic():
    assert mean([2, 4]) == 3


def test_mean_empty_raises():
    with pytest.raises(ValueError):
        mean([])
