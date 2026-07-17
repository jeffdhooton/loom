from loom.executor.agent_plan import AgentPlanClient


def test_agent_plan_client_returns_zero_usage_plan():
    client = AgentPlanClient()
    resp = client.chat.completions.create(model="claude", messages=[{"role": "user", "content": "hi"}])
    assert isinstance(resp.choices[0].message.content, str)
    assert resp.choices[0].message.content  # non-empty
    assert resp.usage.prompt_tokens == 0
    assert resp.usage.completion_tokens == 0
    assert resp.usage.prompt_cache_hit_tokens == 0
