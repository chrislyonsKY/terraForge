# Prompt Templates

Reusable prompts for Claude Code, Copilot, or chat-based AI tools. Copy and adapt as needed.

## Implement a New Domain Function

```
Read CLAUDE.md, then ai-dev/agents/python_expert.md, then ai-dev/guardrails/coding-standards.md.

Implement [function name] in packages/[domain]/src/terraforge/[domain]/[module].py.

Requirements:
- [specific requirement 1]
- [specific requirement 2]

Follow the teach-as-you-build protocol: after writing the function, explain what you wrote, why you made the choices you made, how it connects to the rest of the system, and what to watch for.

Show me the plan first. Do not write code until I type Engage.
```

## Implement a New CLI Command

```
Read CLAUDE.md, then ai-dev/agents/cli_designer.md, then ai-dev/architecture.md (CLI Command Architecture section).

Add the [command name] command to packages/cli/src/terraforge/cli/[domain].py.

The command should call [library function] from packages/[domain] and render the result via terraforge.core.output.

Follow the teach-as-you-build protocol. Show me the plan first. Do not write code until I type Engage.
```

## Review Code for Compliance

```
Read CLAUDE.md, ai-dev/guardrails/, ai-dev/patterns.md.

Review [file or module] for:
- Adherence to project conventions in CLAUDE.md
- Compliance with ai-dev/guardrails/ constraints
- Error handling completeness
- Edge cases
- Async-first pattern (DL-002)
- No direct third-party imports outside core wrappers

Produce a numbered list of findings with severity (Critical / Warning / Info).
```

## Add a Decision Record

```
Read CLAUDE.md, then ai-dev/decisions/ for existing decisions.

I need a decision record for: [topic].

Context: [why this decision is needed]

Create ai-dev/decisions/DL-[next number]-[topic-slug].md following the template in the existing decision records.
```

## End-of-Session Summary

```
Read CLAUDE.md.

Summarize all changes made this session.
Group into logical git commits.
Use format: feat(module): description or fix(module): description

Show proposed commits. Do not run git until I type Engage.
```
