from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass
class CheckResult:
    name: str
    passed: bool
    detail: str


def run_checks(text: str, checks: list[dict]) -> list[CheckResult]:
    """Each entry in `checks` is a single-key dict, e.g. {"max_words": 400}."""
    results: list[CheckResult] = []
    for entry in checks:
        for key, val in entry.items():
            results.append(_run_one(key, val, text))
    return results


def _run_one(key: str, val, text: str) -> CheckResult:
    words = len(text.split())
    if key == "max_words":
        return CheckResult("max_words", words <= val, f"{words} words (limit {val})")
    if key == "min_words":
        return CheckResult("min_words", words >= val, f"{words} words (min {val})")
    if key == "must_contain":
        missing = [s for s in val if s not in text]
        return CheckResult("must_contain", not missing,
                           f"missing: {missing}" if missing else "all present")
    if key == "must_not_contain":
        present = [s for s in val if s in text]
        return CheckResult("must_not_contain", not present,
                           f"forbidden present: {present}" if present else "none present")
    if key == "matches":
        ok = re.search(val, text) is not None
        return CheckResult("matches", ok, f"/{val}/ {'found' if ok else 'NOT found'}")
    return CheckResult(str(key), True, f"unknown check '{key}' — skipped")
