# DL-004: Structured Output Contract

**Date:** 2026-03-12
**Status:** Accepted
**Author:** Chris Lyons

## Context

CLI tools for data work are often used in two distinct contexts: interactively by a developer
reading output in a terminal, and programmatically as part of a pipeline (`jq`, `xargs`,
shell scripts, Python subprocesses). Tools that conflate these two modes — by mixing human
prose with structured data, or by only supporting one output format — cannot serve both.

The naive approach is `print()` statements scattered through the business logic. This is
fast to write and always broken in practice: the output format becomes part of the
implementation rather than a contract, making it impossible to add JSON output later without
rewriting every command.

A second common approach is ad-hoc JSON serialization per command: `json.dumps(some_dict)`.
This produces machine-readable output but no schema, no type safety, and no consistent
field naming across commands.

## Decision

Every EarthForge command returns a **Pydantic BaseModel**. The model is the command's output
contract. The CLI layer passes the model to `earthforge.core.output.render_to_console()`,
which renders it in the format requested by `--output` (`table` | `json` | `csv` | `quiet`).

Business logic never calls `print()`, `rich.print()`, or `typer.echo()`. Commands never
construct dicts or strings for output. The only things that produce terminal output are
the output module and the CLI error handler.

```
command function
    │
    └─► async library function ──► returns Pydantic model
                                          │
                                    render_to_console()
                                          │
                                   ┌──────┴──────┐
                                 table          json
                                 (Rich)        (orjson)
```

## Why Pydantic specifically

Pydantic models give us JSON schema generation, field-level metadata (`title`, `description`)
used by the table renderer to produce human-readable column headers, and validation on
construction that catches bugs at the library boundary rather than in the output layer.
`orjson` serializes Pydantic v2 models natively, so JSON output adds no extra code per command.

## Why a central `output` module rather than per-command rendering

The rendering logic (Rich table formatting, column width heuristics, CSV serialization) is
non-trivial and identical for every command. Centralizing it means: (1) adding a new output
format requires one change in one place, (2) every command automatically gets the new format,
(3) the business logic layer has no dependency on Rich or orjson.

## Consequences

- Every new command must define a Pydantic model for its result. This is a small upfront cost
  that pays off the first time someone pipes `--output json` into `jq`.
- The output module must handle nested models (e.g., a list of `StacItem` inside a
  `SearchResult`) — this is handled by rendering nested models as JSON strings in table mode.
- Commands that produce streaming output (e.g., `stac fetch` progress bars) are exceptions
  to this contract. Progress reporting uses `rich.progress` directly in the CLI layer;
  the final result is still a Pydantic model.

## Alternatives Considered

- **`click`-style formatters**: Would require per-command formatting code. Rejected.
- **Returning dicts**: No schema, no type safety, no IDE support. Rejected.
- **`dataclasses` instead of Pydantic**: No JSON schema generation, no field metadata,
  no native orjson integration. Rejected.
