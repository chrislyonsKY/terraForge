# ai-dev/agents/

Specialized agent configurations for TerraForge development. Each agent reads `CLAUDE.md` first (including the teach-as-you-build protocol), then applies its domain expertise.

| Agent | File | Primary Use |
|---|---|---|
| Solutions Architect | `architect.md` | System design, module interfaces, structural code review |
| Python Expert | `python_expert.md` | Async business logic, data pipelines, library implementation |
| Rust Expert | `rust_expert.md` | PyO3 bindings, maturin builds, performance-critical paths |
| GIS Domain Expert | `gis_domain_expert.md` | Cloud-native format compliance, STAC/COG/GeoParquet patterns |
| CLI Designer | `cli_designer.md` | Typer commands, output formatting, shell ergonomics |
| QA Reviewer | `qa_reviewer.md` | Test strategy, mocking patterns, edge case analysis |

## Usage

Reference from a Claude Code or Copilot prompt:
```
Read CLAUDE.md, then ai-dev/agents/python_expert.md. Implement terraforge.core.storage.
```

## All Agents Must

1. Follow the teach-as-you-build protocol from CLAUDE.md
2. Read guardrails before writing any code
3. Check decision records before proposing alternatives to settled decisions
