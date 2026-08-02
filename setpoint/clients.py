from __future__ import annotations

import os

from openai import OpenAI

DEEPSEEK_BASE = "https://api.deepseek.com"
OLLAMA_BASE = "http://localhost:11434/v1"


def make_deepseek_client() -> OpenAI:
    key = os.environ.get("DEEPSEEK_API_KEY")
    if not key:
        raise SystemExit("DEEPSEEK_API_KEY not set (see .env.example)")
    return OpenAI(base_url=DEEPSEEK_BASE, api_key=key)


def make_judge_client(model: str, engine: str | None = None):
    if engine in ("claude", "codex"):
        from setpoint.gates.agent_judge import AgentJudgeClient
        return AgentJudgeClient(engine=engine)
    # local OMLX/ollama models are free and keyless; DeepSeek judge models reuse the main client
    if model.startswith("deepseek"):
        return make_deepseek_client()
    base = os.environ.get("SETPOINT_JUDGE_BASE_URL", OLLAMA_BASE)
    return OpenAI(base_url=base, api_key="local")
