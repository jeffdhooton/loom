from __future__ import annotations

import os

from openai import OpenAI

DEEPSEEK_BASE = "https://api.deepseek.com"
OMLX_BASE = "http://127.0.0.1:8000/v1"


def make_deepseek_client() -> OpenAI:
    key = os.environ.get("DEEPSEEK_API_KEY")
    if not key:
        raise SystemExit("DEEPSEEK_API_KEY not set (see .env.example)")
    return OpenAI(base_url=DEEPSEEK_BASE, api_key=key)


def make_judge_client(model: str) -> OpenAI:
    # local OMLX models are free and keyless; DeepSeek judge models reuse the main client
    if model.startswith("deepseek"):
        return make_deepseek_client()
    return OpenAI(base_url=OMLX_BASE, api_key="local")
