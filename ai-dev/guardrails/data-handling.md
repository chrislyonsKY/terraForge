# Data Handling Guardrails

## Credentials

- NEVER hardcode API keys, tokens, passwords, or connection strings in source code
- Credentials are resolved at runtime via profile config (`~/.earthforge/config.toml`) or environment variables
- SAS tokens, OAuth tokens, and AWS credentials are resolved by obstore's credential chain — do not implement custom credential resolution
- Test fixtures must not contain real credentials — use placeholder values (`"test-key"`, `"mock-token"`)
- `.env` files are gitignored and never committed

## Cloud Storage

- S3 bucket names, GCS project IDs, and Azure account names are configuration values, not code constants
- All storage paths are validated before use — reject paths containing `..`, shell expansion characters, or control characters
- Presigned URLs must have explicit expiration times — never generate permanent presigned URLs

## User Data

- EarthForge does not collect telemetry, usage analytics, or user data
- Config files are local to the user's machine (`~/.earthforge/`)
- Pipeline YAML may reference credentials via `${env:VAR_NAME}` syntax — the pipeline runner resolves these at runtime, never persists resolved values
