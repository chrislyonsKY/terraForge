# DL-006: Engineering Credibility and Scope Boundaries

**Date:** 2026-03-11
**Status:** Accepted
**Author:** Chris Lyons

## Context

Open-source geospatial projects face a credibility problem. The barrier to generating a scaffold with AI tools is near zero, which means the ecosystem is flooded with repos that have impressive READMEs, complex directory structures, and zero working code. Reviewers, potential contributors, and users have learned to recognize the signals: identical template files across modules, empty directories, generic descriptions, massive initial commits, and scope that claims everything without delivering anything.

EarthForge must be distinguishable from this pattern on first inspection. The difference between an engineered project and a vibe-coded project is not the code itself — it's the evidence of deliberate decision-making at every layer.

## Decision

EarthForge adopts the following principles to signal engineering intent:

### 1. Nothing ships empty

If a directory is in the repo, it contains working code and tests. No skeleton files with TODO markers. No empty `__init__.py` files for packages that don't exist yet. The `packages/cube/` directory appears when cube functionality is implemented, not before. The project structure in CLAUDE.md shows the target architecture — the repo reflects what's built.

### 2. Decisions are documented before code is written

Architecture decisions (this directory) exist because tradeoffs were evaluated. DL-001 explains why monorepo over multi-repo. DL-003 explains why obstore over fsspec. These aren't decorative — they prevent future contributors from re-arguing settled decisions and demonstrate that alternatives were genuinely considered.

### 3. Scope boundaries are explicit and enforced

EarthForge does not include a web server, a database, an ML pipeline, Kubernetes manifests, or Docker Compose files. These exclusions are stated in README.md, CONTRIBUTING.md, and CLAUDE.md. They exist because every feature that's outside scope dilutes focus and signals that the project is trying to be everything, which is the defining characteristic of projects that deliver nothing.

### 4. Git history tells a construction story

The first commits are architecture docs and decision records. Then core interfaces. Then a single working command with tests. Then the next command. Each commit is one logical change with a Conventional Commit message. No "initial commit" blob with hundreds of files. Reviewers who browse the git log should see incremental, deliberate construction.

### 5. AI-assisted code is reviewed, not dumped

AI tools accelerate development. They don't replace engineering judgment. Every function committed to EarthForge must be understood by the person committing it. Generated code that passes tests but can't be explained doesn't belong in the repo.

### 6. Contributing standards are specific, not generic

CONTRIBUTING.md states the actual engineering standards: async-first I/O, structured return types, no print statements, mypy strict, specific commit message format. Not "fork, branch, PR." Specific standards attract contributors who value quality and repel drive-by scaffolding.

## Alternatives Considered

- **Ship fast, polish later** — Rejected. First impressions in open-source are permanent. A repo that launches with empty directories and generic READMEs never recovers its credibility, regardless of how good the code eventually becomes.
- **Minimal docs, maximum code** — Rejected. Code without architecture documentation is opaque to contributors and AI tools alike. The investment in decision records and architecture docs pays compound returns as the project grows.

## Consequences

- Initial development is slower because nothing ships without tests and documentation
- The git history is clean and navigable, which reduces onboarding friction
- Contributors face a higher bar, which filters for quality but may reduce contribution volume
- The project's public-facing artifacts (README, ARCHITECTURE.md, CONTRIBUTING.md, decision records) work together to establish credibility before anyone reads a line of code
- AI coding tools operating in this repo produce better output because the context they read is specific and opinionated, not generic
