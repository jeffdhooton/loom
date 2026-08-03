from __future__ import annotations

DEFAULT_MAX = 6000


def clip(out: str, max_chars: int = DEFAULT_MAX, head: int | None = None) -> str:
    """Middle-elide long output, keeping both ends.

    Failures are printed LAST by test runners, linters and compilers, so a
    head-only truncation drops exactly the part that matters. Keep a small head
    (the command banner / first error) and give the rest of the window to the
    tail. `head` defaults to a quarter of the budget.
    """
    if len(out) <= max_chars:
        return out
    if head is None:
        head = max_chars // 4
    tail = max_chars - head
    dropped = len(out) - max_chars
    return out[:head] + f"\n…[{dropped} chars truncated]…\n" + out[-tail:]
