from setpoint.clients import make_judge_client, OLLAMA_BASE


def test_judge_client_local_points_at_ollama(monkeypatch):
    monkeypatch.delenv("SETPOINT_JUDGE_BASE_URL", raising=False)
    c = make_judge_client("qwen3.6:27b")
    assert str(c.base_url).rstrip("/") == OLLAMA_BASE.rstrip("/")


def test_judge_client_respects_env_override(monkeypatch):
    monkeypatch.setenv("SETPOINT_JUDGE_BASE_URL", "http://127.0.0.1:8000/v1")
    c = make_judge_client("qwen3.6:27b")
    assert "8000" in str(c.base_url)


def test_judge_client_deepseek_uses_main(monkeypatch):
    monkeypatch.setenv("DEEPSEEK_API_KEY", "test-key")
    c = make_judge_client("deepseek-v4-flash")
    assert "deepseek" in str(c.base_url)
