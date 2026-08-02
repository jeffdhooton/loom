from loom.clip import DEFAULT_MAX, clip


def test_short_text_is_untouched():
    assert clip("hello") == "hello"


def test_long_text_keeps_head_and_tail():
    text = "HEAD" + ("x" * 20000) + "TAIL"
    out = clip(text, max_chars=1000)
    assert out.startswith("HEAD")
    assert out.endswith("TAIL")   # the failure line lives here
    assert "truncated" in out
    assert len(out) < 1200


def test_default_head_is_a_quarter_of_the_budget():
    # preserves the CommandGate ratio this helper was extracted from (1500/6000)
    out = clip("a" * 100000)
    head, _, rest = out.partition("\n…[")
    assert len(head) == DEFAULT_MAX // 4
    assert len(rest.split("]…\n", 1)[1]) == DEFAULT_MAX - DEFAULT_MAX // 4


def test_reports_how_much_was_dropped():
    out = clip("a" * 10000, max_chars=1000)
    assert "[9000 chars truncated]" in out
