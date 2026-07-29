from loom.budget import Budget, Usage, PRICING


def test_pricing_has_models():
    assert PRICING["deepseek-v4-pro"]["output"] == 3.48
    assert PRICING["deepseek-v4-flash"]["input"] == 0.14
    assert PRICING["gpt-oss-20b"]["output"] == 0.0


def test_usage_cost_flash():
    u = Usage(input_tokens=1_000_000, output_tokens=1_000_000, cache_read_tokens=0)
    # 0.14 + 0.28
    assert round(u.cost("deepseek-v4-flash", PRICING), 4) == 0.42


def test_usage_cost_with_cache():
    u = Usage(input_tokens=1_000_000, output_tokens=0, cache_read_tokens=1_000_000)
    # cache-read tokens billed at cache_read rate, NOT input rate
    assert round(u.cost("deepseek-v4-flash", PRICING), 4) == 0.028


def test_budget_accumulates_and_stops():
    b = Budget(max_usd=0.50, max_tokens=None, pricing=PRICING)
    b.add("deepseek-v4-flash", Usage(1_000_000, 1_000_000, 0))  # $0.42
    assert b.warn() is True            # 0.42/0.50 = 84%
    assert b.should_stop() is False
    b.add("deepseek-v4-flash", Usage(0, 1_000_000, 0))          # +$0.28 -> $0.70
    assert b.should_stop() is True


def test_budget_token_cap():
    b = Budget(max_usd=None, max_tokens=1_500_000, pricing=PRICING)
    b.add("deepseek-v4-flash", Usage(1_000_000, 0, 0))
    assert b.should_stop() is False
    b.add("deepseek-v4-flash", Usage(600_000, 0, 0))
    assert b.should_stop() is True


def test_no_caps_never_stops():
    b = Budget(max_usd=None, max_tokens=None, pricing=PRICING)
    b.add("deepseek-v4-pro", Usage(9_000_000, 9_000_000, 0))
    assert b.should_stop() is False
    assert b.warn() is False


def test_wall_clock_stop(monkeypatch):
    import loom.budget as b
    clock = {"t": 1000.0}
    monkeypatch.setattr(b.time, "monotonic", lambda: clock["t"])
    budget = b.Budget(max_usd=None, max_tokens=None, pricing=b.PRICING, wall_clock_secs=60)
    assert budget.should_stop() is False
    clock["t"] = 1061.0
    assert budget.should_stop() is True


def test_agent_engines_priced_zero():
    import loom.budget as b
    u = b.Usage(input_tokens=1000, output_tokens=1000)
    assert u.cost("claude", b.PRICING) == 0.0
    assert u.cost("codex", b.PRICING) == 0.0


def test_budget_remaining_secs():
    b = Budget(None, None, PRICING, wall_clock_secs=100)
    r = b.remaining_secs()
    assert r is not None and 90 < r <= 100
    assert Budget(None, None, PRICING).remaining_secs() is None
