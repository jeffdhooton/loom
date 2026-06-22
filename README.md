# loom

A standalone DeepSeek-v4 closed-loop engine. Given a spec file, loom runs
DISCOVER → PLAN → EXECUTE → VERIFY → ITERATE until the work passes its gate
or hits a budget/iteration limit. Progress streams in real time and is
watchable in tmux.

## Install

```bash
python -m venv .venv && . .venv/bin/activate
pip install -e ".[dev]"
```

## Setup

Set `DEEPSEEK_API_KEY` (and `OPENAI_API_KEY` if using a judge gate):

```bash
# Option A — shell export
export DEEPSEEK_API_KEY=sk-...

# Option B — .env file in the repo root (loaded automatically at startup)
cp .env.example .env
# then edit .env
```

## Usage

```bash
loom run examples/coding.loom.yaml          # run a coding loop
loom run examples/content.loom.yaml         # run a content loop
loom run examples/coding.loom.yaml --fresh  # discard prior state and restart
loom ls                                     # list all runs with status + spend
loom logs <name>                            # print the markdown log for a run
```

## Loop specs

A loop spec (`.loom.yaml`) declares everything loom needs: the goal, the
workspace repo, which models to use for planning and execution, the verify
gate (a shell command or an LLM judge with a rubric), stop conditions, and
a budget cap.

`examples/coding.loom.yaml` shows a coding loop that runs pytest as its gate.
`examples/content.loom.yaml` shows a content loop where a judge model scores
the output against a rubric and iterates until the score meets the threshold.

## Local judge (content loops)

Content loops use a local LLM judge via ollama at `http://localhost:11434/v1` (OpenAI-compatible). The default judge model is `qwen3.6:27b`. To override the endpoint, set `LOOM_JUDGE_BASE_URL` (e.g. `export LOOM_JUDGE_BASE_URL=http://127.0.0.1:8000/v1` to point at OMLX instead). Thinking models (such as qwen3) are handled automatically — loom passes `reasoning_effort: "none"` so they return clean JSON rather than empty content. DeepSeek judge models skip ollama and reuse the main DeepSeek client.

## Security note

loom executes model-generated shell commands and file writes inside the
configured workspace repo. Confinement is workspace-level (the cwd is set
to the repo), not a strict sandbox. Run loom only on repos or worktrees you
trust — treat it the same as running an AI coding agent on your machine.
