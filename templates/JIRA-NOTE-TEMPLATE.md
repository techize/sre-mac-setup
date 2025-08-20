# Jira Note Template (Local Tooling + Context)

Use this comment in the ticket when adding local, optional checks to a repo.

What

- Added local-only pre-commit hooks using PATH tools (no CI enforcement)
  - `sp-guard-prod` (guard protected files – uses `.sp-guard.yml` if present)
  - `sp-helm-check` (lint + template validation where applicable)

Why

- Provide consistent guardrails and fast feedback without changing pipelines
- Prevent accidental edits to critical files (e.g., production values)

How

- Updated `.pre-commit-config.yaml` to call PATH tools; they no-op if not installed
- Added `.sp-guard.yml` with protected paths: <list paths or write “N/A”>

Scope

- Local developer experience only; CI pipelines unchanged
- Safe to ignore if tools not installed locally

Follow-up / TODO

- Extend protected paths if needed
- Consider documenting repo-specific paths in `CONTRIBUTING.md`

Setup for Developers

- Ensure `~/bin` is on PATH
- Run `./bin/sp-tools install` in sre-mac-setup
- Optional: run checks manually: `sp-helm-check` / `sp-guard-prod`
