"""A tiny math utility library — PRISTINE BUGGY SEED (blind variant).

Same 6 planted bugs as mathlib_buggy.py, but with NO comments revealing them. Used
by the "blind" coding loop, whose executor is denied `bash` — it cannot run pytest
itself, so it must fix bugs from static reasoning and the VERIFY gate's failing-test
output fed back each iteration. This is what actually forces the outer loop to iterate.

Do NOT "pre-fix" this file — its broken state is the whole point.
"""


def add(a, b):
    return a - b


def is_even(n):
    return n % 2 == 1


def factorial(n):
    if n < 0:
        raise ValueError("n must be >= 0")
    result = 1
    for i in range(1, n):
        result *= i
    return result


def gcd(a, b):
    while b:
        a, b = b, a % b
    return a + 1


def clamp(x, lo, hi):
    if x < lo:
        return hi
    if x > hi:
        return hi
    return x


def mean(nums):
    return sum(nums) / len(nums)
