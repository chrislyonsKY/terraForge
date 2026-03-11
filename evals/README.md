# evals/

Prompt evaluation infrastructure using [promptfoo](https://www.promptfoo.dev/). Tests that TerraForge's AI development docs (agents, templates, guardrails) produce correct, consistent, and safe output across models.

## Eval Suites

| Suite | Config | What It Tests | CI Gate |
|---|---|---|---|
| Agent Prompts | `promptfooconfig.yaml` | Do agent prompts produce code following async-first, structured-return, no-print conventions? | Hard fail — blocks merge |
| Red-Team | `promptfooconfig.redteam.yaml` | Can adversarial prompts trick the agent into violating guardrails (eval/exec, hardcoded creds, fsspec, print)? | Hard fail — blocks merge |
| Templates | `promptfooconfig.templates.yaml` | Do prompt templates produce consistent, plan-first output across models? | Soft fail — warning only |

## Models

All suites evaluate against:
- **Claude Opus 4** (`anthropic:messages:claude-opus-4-6`)
- **GPT-4o** (`openai:gpt-4o`)

## Running Locally

```bash
# Prerequisites
npm install -g promptfoo   # or: brew install promptfoo
export ANTHROPIC_API_KEY=your-key
export OPENAI_API_KEY=your-key

# Run all suites
cd evals
promptfoo eval -c promptfooconfig.yaml
promptfoo eval -c promptfooconfig.redteam.yaml
promptfoo eval -c promptfooconfig.templates.yaml

# View results in browser
promptfoo view
```

## CI/CD

The `.github/workflows/prompt-eval.yml` workflow runs on PRs that modify:
- `ai-dev/agents/**`
- `ai-dev/guardrails/**`
- `ai-dev/prompt-templates.md`
- `CLAUDE.md`
- `.github/copilot-instructions.md`
- `evals/**`

Agent and red-team suites hard-fail the PR. Template suite warns but doesn't block.

## Adding New Tests

Add test cases to the appropriate `promptfooconfig.*.yaml` file. Each test needs:
- `description` — what you're testing
- `vars` — the task/input for the prompt
- `assert` — mix of string checks (`contains`, `not-icontains`) and semantic checks (`llm-rubric`)

For red-team tests, the assertion logic is inverted: a "pass" means the guardrail held (the model refused the adversarial request).

## Custom Assertions

JavaScript assertion files live in `assertions/`. They receive `(output, context)` and return `{ pass, score, reason }`. Use these for structural code checks that `llm-rubric` can't reliably catch (e.g., counting `print()` calls in code blocks, checking import patterns).
