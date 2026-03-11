# DL-007: promptfoo for Agent Prompt and Guardrail Evaluation

**Date:** 2026-03-11
**Status:** Accepted
**Author:** Chris Lyons

## Context

EarthForge's `ai-dev/` infrastructure (agent prompts, guardrails, prompt templates) is code — it directly determines the quality of AI-generated output. Changes to CLAUDE.md, agent configurations, or guardrail wording can silently degrade the code that agents produce. There's no automated way to detect when an edit to `ai-dev/agents/python_expert.md` causes the agent to stop producing async-first code or start using `print()` in library modules.

## Decision

Use promptfoo as the evaluation framework for EarthForge's AI development infrastructure. Three eval suites run in CI on every PR that touches `ai-dev/`, `CLAUDE.md`, `copilot-instructions.md`, or `evals/`:

1. **Agent Prompt Eval** — Feeds agent system prompts + coding tasks to Claude Opus 4 and GPT-4o, then checks output for structural code patterns (async-first, structured returns, error handling, no direct imports) via JavaScript assertions and semantic checks via llm-rubric.

2. **Guardrail Red-Team** — Sends adversarial prompts that attempt to trick the agent into violating constraints (eval/exec injection, hardcoded credentials, print in library code, fsspec usage, business logic in CLI, hatchling for Rust, sync-first APIs). A pass means the guardrail held.

3. **Template Consistency** — Tests that prompt templates from `ai-dev/prompt-templates.md` produce plan-first, Engage-gated output consistently across models.

Agent and red-team suites hard-fail the PR. Template suite issues a warning.

## Alternatives Considered

- **Manual review only** — Rejected. Agent prompt changes are subtle — a removed sentence can break a convention across all generated code. Automated eval catches regressions that human review misses.
- **Custom Python test harness** — Rejected. promptfoo provides declarative YAML configs, built-in multi-model support, llm-rubric semantic assertions, HTML report generation, CI integration, and caching out of the box. Building this from scratch would duplicate significant functionality.
- **Braintrust / Langfuse** — Rejected. Both are broader observability platforms with heavier integration requirements. promptfoo is CLI-first, open-source, runs locally, and fits the "composable developer toolkit" philosophy.

## Consequences

- Agent prompt changes are regression-tested before merge
- Guardrail violations are caught automatically, not just by code review
- CI requires `ANTHROPIC_API_KEY` and `OPENAI_API_KEY` secrets for eval runs
- Eval cost per PR: approximately $2-5 depending on test count (cost assertions cap at $0.50/test)
- promptfoo is a Node.js dependency (`npx promptfoo@latest`) — no Python installation required for evals
- llm-rubric assertions use an LLM judge, introducing non-determinism — results may vary between runs. JavaScript assertions provide deterministic structural checks as the primary gate.
