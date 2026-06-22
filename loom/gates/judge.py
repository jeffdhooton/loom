from __future__ import annotations

import json
from pathlib import Path
from typing import Callable

from . import Gate, GateResult
from .checks import run_checks

_PROMPT = """You are a strict reviewer. Grade the ARTIFACT against the RUBRIC.
First extract each distinct rubric criterion. For EACH criterion, decide pass or fail
and cite SPECIFIC evidence from the artifact (a quote, a count, a concrete observation).
Be skeptical: never mark a criterion pass without concrete evidence. If a criterion is
about length or counts, actually count.

Return ONLY compact JSON, no prose:
{{"criteria": [{{"name": "<criterion>", "pass": <true|false>, "evidence": "<specifics>"}}],
  "score": <float 0..1>, "feedback": "<what to fix>"}}

RUBRIC:
{rubric}

ARTIFACT:
{artifact}
"""


class JudgeGate(Gate):
    def __init__(self, client, model: str, rubric_text: str, threshold: float,
                 artifact: str | None, extra_body: dict | None = None,
                 checks: list[dict] | None = None):
        self.client = client
        self.model = model
        self.rubric_text = rubric_text
        self.threshold = threshold
        self.artifact = artifact
        self.extra_body = extra_body
        self.checks = checks or []

    def _read_artifact(self, cwd: Path) -> str:
        path = Path(self.artifact) if self.artifact else None
        if path and not path.is_absolute():
            path = cwd / path
        return path.read_text() if path and path.exists() else "[no artifact produced]"

    def verify(self, cwd: Path, on_event: Callable) -> GateResult:
        text = self._read_artifact(cwd)

        # Layer 1: deterministic checks (free, reliable). Fail fast, no LLM call.
        check_results = run_checks(text, self.checks)
        failed = [c for c in check_results if not c.passed]
        if failed:
            on_event({"kind": "verify_start", "checks": "failed"})
            detail = "; ".join(f"{c.name}: {c.detail}" for c in failed)
            return GateResult(passed=False,
                              feedback=f"Deterministic checks failed: {detail}", score=None)

        # Layer 2: structured LLM judge for subjective criteria.
        on_event({"kind": "verify_start", "judge": self.model})
        prompt = _PROMPT.format(rubric=self.rubric_text, artifact=text[:20000])
        kwargs = {"model": self.model, "messages": [{"role": "user", "content": prompt}]}
        if self.extra_body:
            kwargs["extra_body"] = self.extra_body
        resp = self.client.chat.completions.create(**kwargs)
        content = resp.choices[0].message.content or "{}"
        try:
            data = json.loads(content[content.find("{"): content.rfind("}") + 1])
            score = float(data.get("score", 0.0))
            feedback = str(data.get("feedback", ""))
            criteria = data.get("criteria", []) or []
        except (ValueError, json.JSONDecodeError):
            return GateResult(passed=False,
                              feedback=f"judge returned non-JSON: {content[:200]}", score=0.0)

        failed_criteria = [c.get("name", "?") for c in criteria
                           if isinstance(c, dict) and c.get("pass") is False]
        passed = score >= self.threshold and not failed_criteria
        if failed_criteria:
            feedback = f"failed criteria: {failed_criteria}. {feedback}"
        passed_checks = [f"{c.name}: {c.detail}" for c in check_results]
        if passed_checks:
            feedback = f"[checks ok: {'; '.join(passed_checks)}] {feedback}"
        return GateResult(passed=passed, feedback=feedback, score=score)
