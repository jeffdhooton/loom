from __future__ import annotations

import json
from pathlib import Path
from typing import Callable

from loom.budget import Usage
from loom.tools import Tool, ToolContext
from .base import ExecEvent, ExecuteResult, Executor


class DeepSeekExecutor(Executor):
    def __init__(self, client, pricing: dict, max_turns: int = 25):
        self.client = client
        self.pricing = pricing
        self.max_turns = max_turns

    def execute(self, system: str, task: str, tools: list[Tool], model: str,
                cwd: Path, on_event: Callable[[ExecEvent], None]) -> ExecuteResult:
        by_name = {t.name: t for t in tools}
        schemas = [t.schema for t in tools]
        ctx = ToolContext(cwd=cwd)
        messages = [
            {"role": "system", "content": system},
            {"role": "user", "content": task},
        ]
        usage = Usage()
        steps: list[dict] = []

        for _turn in range(self.max_turns):
            kwargs = {"model": model, "messages": messages}
            if schemas:
                kwargs["tools"] = schemas  # NOTE: never set tool_choice (unsupported)
            resp = self.client.chat.completions.create(**kwargs)

            u = resp.usage
            cache = getattr(u, "prompt_cache_hit_tokens", 0) or 0
            usage.input_tokens += getattr(u, "prompt_tokens", 0) or 0
            usage.output_tokens += getattr(u, "completion_tokens", 0) or 0
            usage.cache_read_tokens += cache

            msg = resp.choices[0].message
            tool_calls = getattr(msg, "tool_calls", None)

            if not tool_calls:
                text = msg.content or ""
                on_event(ExecEvent("assistant", {"text": text}))
                return ExecuteResult(text=text, usage=usage, steps=steps)

            # Echo the assistant message back, INCLUDING reasoning_content
            # (DeepSeek reasoning models require it for tool-call continuations).
            assistant_msg = {
                "role": "assistant",
                "content": msg.content,
                "tool_calls": [
                    {"id": tc.id, "type": "function",
                     "function": {"name": tc.function.name,
                                  "arguments": tc.function.arguments}}
                    for tc in tool_calls
                ],
            }
            rc = getattr(msg, "reasoning_content", None)
            if rc is not None:
                assistant_msg["reasoning_content"] = rc
            messages.append(assistant_msg)

            for tc in tool_calls:
                name = tc.function.name
                try:
                    args = json.loads(tc.function.arguments or "{}")
                except json.JSONDecodeError:
                    args = {}
                on_event(ExecEvent("tool", {"name": name, "args": args}))
                if name in by_name:
                    result = by_name[name].run(args, ctx)
                else:
                    result = f"ERROR: unknown tool {name}"
                steps.append({"tool": name, "args": args, "result": result})
                messages.append({
                    "role": "tool",
                    "tool_call_id": tc.id,
                    "content": result,
                })

        return ExecuteResult(
            text="[executor stopped: hit max tool turns]", usage=usage, steps=steps)
