from types import SimpleNamespace

from loom.executor.base import ExecEvent
from loom.executor.deepseek import DeepSeekExecutor
from loom.tools import build_registry
from loom.budget import PRICING


def _msg(content=None, tool_calls=None, reasoning_content=None):
    return SimpleNamespace(content=content, tool_calls=tool_calls,
                           reasoning_content=reasoning_content, role="assistant")


def _tool_call(cid, name, arguments):
    return SimpleNamespace(id=cid, type="function",
                           function=SimpleNamespace(name=name, arguments=arguments))


def _resp(message, pt=10, ct=5, cache=0):
    usage = SimpleNamespace(prompt_tokens=pt, completion_tokens=ct,
                            prompt_cache_hit_tokens=cache)
    return SimpleNamespace(choices=[SimpleNamespace(message=message)], usage=usage)


class FakeClient:
    """Returns queued responses; records the messages it was called with."""
    def __init__(self, responses):
        self._responses = list(responses)
        self.calls = []
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self._create))

    def _create(self, **kw):
        self.calls.append(kw)
        return self._responses.pop(0)


def test_executor_runs_tool_then_finishes(tmp_path):
    # turn 1: model asks to write a file; turn 2: model returns final text
    tc = _tool_call("call_1", "write",
                    '{"path": "out.txt", "content": "hi"}')
    client = FakeClient([
        _resp(_msg(content="thinking", tool_calls=[tc], reasoning_content="rc"), pt=100, ct=20),
        _resp(_msg(content="done — wrote the file"), pt=50, ct=10),
    ])
    ex = DeepSeekExecutor(client=client, pricing=PRICING)
    tools = build_registry(["write"])

    events = []
    result = ex.execute(system="sys", task="write hi to out.txt",
                        tools=tools, model="deepseek-v4-flash",
                        cwd=tmp_path, on_event=events.append)

    assert result.text == "done — wrote the file"
    assert (tmp_path / "out.txt").read_text() == "hi"
    # usage accumulated across both turns: pt 150, ct 30
    assert result.usage.input_tokens == 150
    assert result.usage.output_tokens == 30
    # a tool event was emitted
    assert any(e.kind == "tool" and e.data["name"] == "write" for e in events)


def test_executor_echoes_reasoning_content_on_assistant_turn(tmp_path):
    tc = _tool_call("call_1", "write", '{"path": "f", "content": "x"}')
    client = FakeClient([
        _resp(_msg(content="c", tool_calls=[tc], reasoning_content="MY_REASONING")),
        _resp(_msg(content="ok")),
    ])
    ex = DeepSeekExecutor(client=client, pricing=PRICING)
    ex.execute("s", "t", build_registry(["write"]), "deepseek-v4-flash",
               tmp_path, lambda e: None)

    # second create() call must include the assistant message carrying reasoning_content
    second_msgs = client.calls[1]["messages"]
    assistant = [m for m in second_msgs if m["role"] == "assistant"][0]
    assert assistant["reasoning_content"] == "MY_REASONING"
    tool_reply = [m for m in second_msgs if m["role"] == "tool"][0]
    assert tool_reply["tool_call_id"] == "call_1"


def test_executor_does_not_force_tool_choice(tmp_path):
    client = FakeClient([_resp(_msg(content="immediate answer"))])
    ex = DeepSeekExecutor(client=client, pricing=PRICING)
    ex.execute("s", "t", build_registry(["read"]), "deepseek-v4-pro",
               tmp_path, lambda e: None)
    assert "tool_choice" not in client.calls[0]


def test_executor_caps_tool_turns(tmp_path):
    # model loops forever asking for tools; executor must bail at max_turns
    tc = _tool_call("c", "read", '{"path": "x"}')
    responses = [_resp(_msg(content="loop", tool_calls=[tc])) for _ in range(50)]
    client = FakeClient(responses)
    ex = DeepSeekExecutor(client=client, pricing=PRICING, max_turns=5)
    result = ex.execute("s", "t", build_registry(["read"]), "deepseek-v4-flash",
                        tmp_path, lambda e: None)
    assert "stopped" in result.text.lower() or "max" in result.text.lower()
    assert len(client.calls) == 5
