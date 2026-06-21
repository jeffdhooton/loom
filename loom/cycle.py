from __future__ import annotations

from pathlib import Path

from loom.budget import Budget, Usage
from loom.memory import IterRecord, Memory, RunState
from loom.tools import build_registry

_PLAN_PROMPT = """You are the PLAN stage of a closed loop.
Goal: {goal}

Context:
{context}

{history}

The last verification {verdict}.
{feedback_block}
Produce a short, concrete plan for THIS iteration only — what to change/do next.
"""

_EXEC_SYSTEM = """You are the EXECUTE stage of a closed loop working toward this goal:
{goal}

Use the provided tools to do the work in the workspace. When the planned step is
complete, stop and briefly state what you did. Do not ask questions."""


class Cycle:
    def __init__(self, spec, executor, gate, memory: Memory, budget: Budget, ui,
                 plan_client):
        self.spec = spec
        self.executor = executor
        self.gate = gate
        self.memory = memory
        self.budget = budget
        self.ui = ui
        self.plan_client = plan_client

    def _discover(self) -> str:
        parts = [self.spec.context.notes] if self.spec.context.notes else []
        for f in self.spec.context.files:
            p = self.spec.workspace.repo / f
            if p.exists():
                parts.append(f"### {f}\n{p.read_text()[:4000]}")
        parts.append(self.memory.context_block())
        return "\n\n".join(parts)

    def _plan(self, context: str, last: IterRecord | None) -> tuple[str, Usage]:
        verdict = "failed" if last and not last.passed else "has not run yet"
        feedback_block = f"Failure feedback:\n{last.feedback}\n" if last and not last.passed else ""
        prompt = _PLAN_PROMPT.format(
            goal=self.spec.goal, context=context,
            history=self.memory.context_block(), verdict=verdict,
            feedback_block=feedback_block)
        resp = self.plan_client.chat.completions.create(
            model=self.spec.execute.plan_model,
            messages=[{"role": "user", "content": prompt}],
        )
        u = resp.usage
        usage = Usage(getattr(u, "prompt_tokens", 0) or 0,
                      getattr(u, "completion_tokens", 0) or 0,
                      getattr(u, "prompt_cache_hit_tokens", 0) or 0)
        return resp.choices[0].message.content or "", usage

    def run(self, cwd: Path) -> RunState:
        self.memory.start()
        tools = build_registry(self.spec.execute.tools)
        last: IterRecord | None = None
        no_progress = 0

        for n in range(1, self.spec.stop.max_iters + 1):
            if self.budget.should_stop():
                self.memory.set_status("budget_exhausted")
                break

            # DISCOVER
            self.ui.stage("DISCOVER", n, self.spec.stop.max_iters)
            context = self._discover()

            # PLAN
            self.ui.stage("PLAN", n, self.spec.stop.max_iters)
            plan, plan_usage = self._plan(context, last)
            self.budget.add(self.spec.execute.plan_model, plan_usage)

            # EXECUTE
            self.ui.stage("EXECUTE", n, self.spec.stop.max_iters)
            result = self.executor.execute(
                system=_EXEC_SYSTEM.format(goal=self.spec.goal),
                task=f"Plan for this iteration:\n{plan}",
                tools=tools, model=self.spec.execute.model, cwd=cwd,
                on_event=lambda e: self.ui.tool(e.data.get("name", ""), e.data.get("args", {}))
                if e.kind == "tool" else None,
            )
            self.budget.add(self.spec.execute.model, result.usage)

            # VERIFY
            self.ui.stage("VERIFY", n, self.spec.stop.max_iters)
            gate_result = self.gate.verify(cwd=cwd, on_event=lambda e: None)
            self.ui.verify(gate_result)

            iter_usd = (plan_usage.cost(self.spec.execute.plan_model, self.budget.pricing)
                        + result.usage.cost(self.spec.execute.model, self.budget.pricing))
            rec = IterRecord(n=n, plan=plan, summary=result.text,
                             passed=gate_result.passed, feedback=gate_result.feedback,
                             usd=iter_usd, score=gate_result.score)
            self.memory.append(rec)

            # ITERATE
            if gate_result.passed:
                self.memory.set_status("passed")
                last = rec
                break

            # no-progress tracking: feedback unchanged from prior failing iter
            if last is not None and last.feedback == rec.feedback:
                no_progress += 1
            else:
                no_progress = 0
            last = rec
            if (self.spec.stop.no_progress_after is not None
                    and no_progress + 1 >= self.spec.stop.no_progress_after):
                self.memory.set_status("stopped")
                break
        else:
            self.memory.set_status("stopped")

        state = self.memory.load()
        self.ui.summary(state)
        return state
