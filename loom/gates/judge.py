from __future__ import annotations

import json
from pathlib import Path
from typing import Callable

from . import Gate, GateResult

_PROMPT = """You are a strict reviewer. Grade the ARTIFACT against the RUBRIC.
Return ONLY compact JSON: {{"score": <float 0..1>, "feedback": "<what to fix>"}}.

RUBRIC:
{rubric}

ARTIFACT:
{artifact}
"""


class JudgeGate(Gate):
    def __init__(self, client, model: str, rubric_text: str, threshold: float,
                 artifact: str | None):
        self.client = client
        self.model = model
        self.rubric_text = rubric_text
        self.threshold = threshold
        self.artifact = artifact

    def verify(self, cwd: Path, on_event: Callable) -> GateResult:
        on_event({"kind": "verify_start", "judge": self.model})
        path = Path(self.artifact) if self.artifact else None
        if path and not path.is_absolute():
            path = cwd / path
        text = path.read_text() if path and path.exists() else "[no artifact produced]"
        prompt = _PROMPT.format(rubric=self.rubric_text, artifact=text[:20000])
        resp = self.client.chat.completions.create(
            model=self.model,
            messages=[{"role": "user", "content": prompt}],
        )
        content = resp.choices[0].message.content or "{}"
        try:
            data = json.loads(content[content.find("{"): content.rfind("}") + 1])
            score = float(data.get("score", 0.0))
            feedback = str(data.get("feedback", ""))
        except (ValueError, json.JSONDecodeError):
            return GateResult(passed=False, feedback=f"judge returned non-JSON: {content[:200]}",
                              score=0.0)
        return GateResult(passed=score >= self.threshold, feedback=feedback, score=score)
