"""A tiny math utility library — PRISTINE BUGGY SEED for the loom stress sweep.

This file is copied to `mathlib.py` inside the (gitignored) stress sandboxes by
`setup.sh`. It contains 6 independent, deliberately-planted bugs spread across the
functions so that `pytest -q` surfaces several failures at once. The loom coding
loop must read the pytest output, fix the bugs, and re-verify across iterations.

Do NOT "pre-fix" this file — its broken state is the whole point.
"""


def add(a, b):
    return a - b  # BUG 1: should be a + b


def is_even(n):
    return n % 2 == 1  # BUG 2: should be == 0


def factorial(n):
    if n < 0:
        raise ValueError("n must be >= 0")
    result = 1
    for i in range(1, n):  # BUG 3: range should be range(1, n + 1)
        result *= i
    return result


def gcd(a, b):
    while b:
        a, b = b, a % b
    return a + 1  # BUG 4: should be return a


def clamp(x, lo, hi):
    if x < lo:
        return hi  # BUG 5: should return lo
    if x > hi:
        return hi
    return x


def mean(nums):
    # BUG 6: empty input should raise ValueError, not ZeroDivisionError
    return sum(nums) / len(nums)
