# Contributing – Local Optional Tooling

This repo uses optional, local developer tooling. Nothing is enforced in CI. Install once and it will be available across repos via PATH.

## Why

- Consistent local checks without slowing down CI
- Guardrails for risky edits (e.g., production values)
- Fast Helm validation while iterating

## Install

1. Ensure `~/bin` is on your PATH (in `~/.zshrc`):

   export PATH="$HOME/bin:$PATH"

2. From sre-mac-setup, link tools:

   ./bin/sp-tools install

## Hooks used here (optional)

- Guard protected files on commit: `sp-guard-prod` (respects `.sp-guard.yml`)
- Helm checks on push: `sp-helm-check`

### pre-commit snippet

Add this to `.pre-commit-config.yaml` in your repo:

```yaml
repos:
  - repo: local
    hooks:
      - id: guard-production-values
        name: Guard protected files on commit (local)
        entry: bash
        args: [ -lc, 'command -v sp-guard-prod >/dev/null || { echo "sp-guard-prod not installed; skipping" >&2; exit 0; }; sp-guard-prod' ]
        language: system
        pass_filenames: false
        stages: [commit]

      - id: helm-lint-template
        name: Helm lint & template (local)
        entry: bash
        args: [ -lc, 'command -v sp-helm-check >/dev/null || { echo "sp-helm-check not installed; skipping" >&2; exit 0; }; sp-helm-check' ]
        language: system
        pass_filenames: false
        stages: [push]
```

### Protected paths

Declare protected files in `.sp-guard.yml` at repo root:

```yaml
protected:
  - path/to/critical/values.production.yaml
  - another/protected/file
```

Notes:

- If `sp-guard-prod` isn’t installed, hooks print a skip message and do not block.
- Override guard intentionally via `ALLOW_PROD_VALUES=1` or use release/hotfix branches.
