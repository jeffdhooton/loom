"""HIDDEN acceptance oracle for the romans library (Stage 4).

This file lives OUTSIDE the loop's worktree and is run by the command gate via
  PYTHONPATH=. pytest <this file> -q
so `import romans` resolves to the module the agent is editing in its worktree.
The agent cannot read or run this file — its only signal is pytest's failure
output, fed back each iteration. The strict-validation cases below are the ones
a first blind attempt typically misses, forcing genuine self-correction.
"""

import pytest

from romans import to_roman, from_roman, is_valid


# ---- to_roman: canonical encoding ------------------------------------------

@pytest.mark.parametrize("n,expected", [
    (1, "I"), (3, "III"), (4, "IV"), (9, "IX"), (14, "XIV"),
    (40, "XL"), (90, "XC"), (49, "XLIX"), (400, "CD"), (900, "CM"),
    (444, "CDXLIV"), (1994, "MCMXCIV"), (2024, "MMXXIV"),
    (3888, "MMMDCCCLXXXVIII"), (3999, "MMMCMXCIX"),
])
def test_to_roman_canonical(n, expected):
    assert to_roman(n) == expected


@pytest.mark.parametrize("bad", [0, -1, 4000, 5000])
def test_to_roman_out_of_range_raises(bad):
    with pytest.raises(ValueError):
        to_roman(bad)


@pytest.mark.parametrize("bad", [2.5, "X", None, True])
def test_to_roman_non_int_raises(bad):
    # bools are not acceptable integers here either.
    with pytest.raises((ValueError, TypeError)):
        to_roman(bad)


# ---- from_roman: parse valid, reject invalid -------------------------------

@pytest.mark.parametrize("s,expected", [
    ("I", 1), ("IV", 4), ("IX", 9), ("XL", 40), ("XC", 90),
    ("CD", 400), ("CM", 900), ("MCMXCIV", 1994), ("MMXXIV", 2024),
    ("MMMCMXCIX", 3999),
])
def test_from_roman_valid(s, expected):
    assert from_roman(s) == expected


@pytest.mark.parametrize("bad", [
    "", "IIII", "VV", "LL", "DD", "MMMM",   # illegal repetition
    "IL", "IC", "XM", "VX", "IIV",          # illegal subtractive pairs / order
    "iv", "Xx", "mmxxiv",                   # lowercase not allowed
    "ABC", "I I", "IVI", "MCMC",            # junk / non-canonical
])
def test_from_roman_invalid_raises(bad):
    with pytest.raises(ValueError):
        from_roman(bad)


# ---- is_valid --------------------------------------------------------------

@pytest.mark.parametrize("s", ["I", "IV", "MMXXIV", "MMMCMXCIX"])
def test_is_valid_true(s):
    assert is_valid(s) is True


@pytest.mark.parametrize("s", ["", "IIII", "IL", "iv", "ABC", "MMMM"])
def test_is_valid_false(s):
    assert is_valid(s) is False


# ---- round-trip across the whole supported range ---------------------------

def test_round_trip_all():
    for n in range(1, 4000):
        assert from_roman(to_roman(n)) == n
