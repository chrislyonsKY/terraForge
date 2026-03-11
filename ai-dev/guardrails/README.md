# ai-dev/guardrails/

Hard constraints that override all other guidance. When a guardrail conflicts with an agent suggestion, the guardrail wins.

| Guardrail | File | Scope |
|---|---|---|
| Coding Standards | `coding-standards.md` | Python style, async patterns, import rules, testing |
| Data Handling | `data-handling.md` | Credentials, storage paths, user data |
| Cloud-Native Compliance | `cloud-native-compliance.md` | STAC, COG, GeoParquet, Zarr, FlatGeobuf specs |

Read all three before writing any code.
