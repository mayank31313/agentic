# Contributing to Agentic

Thanks for your interest in contributing to **Agentic**! This document explains how to set up your environment, propose changes, and submit contributions — whether directly to this repository or via a fork.

By contributing, you agree that your contributions will be licensed under the project's [LICENSE](LICENSE) (MIT License with Attribution Requirement), and that any fork or derivative work you publish must keep the required attribution to the original author, Mayank Shinde, and the original project.

## Table of contents

- [Code of conduct](#code-of-conduct)
- [Ways to contribute](#ways-to-contribute)
- [Project setup](#project-setup)
- [Development workflow](#development-workflow)
- [Coding guidelines](#coding-guidelines)
- [Commit message conventions](#commit-message-conventions)
- [Testing](#testing)
- [Submitting a pull request](#submitting-a-pull-request)
- [Forking the project](#forking-the-project)
- [Reporting bugs & requesting features](#reporting-bugs--requesting-features)
- [Attribution requirement](#attribution-requirement)

## Code of conduct

Be respectful and constructive. Assume good intent, give actionable feedback, and keep discussions focused on the technical merits of a change. Harassment, discrimination, or abusive behavior will not be tolerated.

## Ways to contribute

You don't have to write code to contribute:

- **Bug reports** — clear, reproducible issues help a lot.
- **Feature requests / ideas** — open a discussion or issue describing the use case.
- **Documentation** — improve the README, `architecture.md`, or add examples.
- **New skills** — add a `SKILL.md` under `src/skills/`.
- **New MCP tool servers / integrations** — e.g. a new service under `src/agentic/agentic_mcp/`.
- **New channel adapters** — e.g. Slack/Discord alongside the existing Telegram adapter.
- **Bug fixes and features** — see open issues labeled `good first issue` or `help wanted`.

## Project setup

### Prerequisites

- Python 3.14+
- [uv](https://docs.astral.sh/uv/) for dependency management
- Git
- Docker & Docker Compose (optional, for containerized testing)

### Clone and install

```powershell
git clone https://github.com/mayank31313/agentic.git
cd agentic
uv sync
```

### Run the bot locally

```powershell
uv run agentic run
```

See the [README](README.md) for full configuration details (`resources/agentic.json`, `resources/application.yml`, environment variables, Docker Compose, etc.).

## Development workflow

1. **Create a branch** off `main` with a descriptive name:
   ```powershell
   git checkout -b feature/short-description
   # or: fix/short-description, docs/short-description, chore/short-description
   ```
2. **Make your changes**, keeping commits focused and logically scoped.
3. **Add/update tests** under `tests/` for any behavior change.
4. **Run lint and tests** locally before pushing (see [Testing](#testing)).
5. **Update documentation** (README, `architecture.md`, docstrings) if your change affects usage, configuration, or architecture.
6. **Push your branch** and open a pull request against `main`.

## Coding guidelines

- Follow existing code style and structure; keep modules under `src/agentic/` organized the way they already are (`app/`, `agentic_mcp/`, `cli/`, `websocket_client/`).
- Prefer small, composable functions/classes over large monoliths.
- Use type hints where practical.
- Run `ruff` (already configured via `.ruff_cache/`) to catch lint issues:
  ```powershell
  uv run ruff check .
  ```
- Keep configuration-driven behavior in `resources/agentic.json` / `resources/application.yml` rather than hardcoding values in code, consistent with the project's config-first philosophy.
- New tools/integrations should be added as MCP servers under `src/agentic/agentic_mcp/<your_tool>/` and registered in `resources/agentic.json` under `mcpServers`, per the [README's extension guide](README.md#extending-agentic).
- Never commit secrets, tokens, or credentials. Use `resources/application.yml` references (env vars or Vault) instead, and keep real credentials out of `credentials/` in version control.

## Commit message conventions

Use clear, imperative commit messages, ideally following a lightweight [Conventional Commits](https://www.conventionalcommits.org/) style:

```
feat: add Slack channel adapter
fix: correct cron schedule parsing for weekly jobs
docs: update README with Vault secrets example
chore: bump deepagents dependency
refactor: extract memory compaction into its own module
test: add coverage for scheduler edge cases
```

## Testing

Tests live under `tests/` and use `pytest`.

```powershell
uv sync --group test
uv run pytest
```

Please ensure:
- New features include unit tests where feasible.
- Existing tests pass before opening a PR.
- Bug fixes include a regression test when possible.

## Submitting a pull request

1. Ensure your branch is up to date with `main` (rebase or merge as needed).
2. Open a PR with:
   - A clear title and description of **what** changed and **why**.
   - Linked issue(s), if applicable (`Closes #123`).
   - Notes on testing performed.
   - Screenshots/logs for behavior changes where helpful (e.g. Telegram interactions, CLI output).
3. Be responsive to review feedback — small, iterative commits are fine during review.
4. A maintainer will merge once the PR is approved and CI (if configured) passes.

## Forking the project

You're welcome to fork Agentic to experiment, build your own assistant, or maintain a long-term variant. If you fork or redistribute this project:

1. **Keep the [LICENSE](LICENSE) file intact** in your fork.
2. **Retain attribution** to the original author, Mayank Shinde, and the original "Agentic" project, per the license's Attribution clause — e.g. in your fork's README ("Based on / forked from Agentic by Mayank Shinde"), an "About"/"Credits" section, or your app's documentation.
3. Clearly mark your fork as a derivative work if you rename or substantially change its purpose, so users can distinguish it from the upstream project.
4. Consider opening a PR upstream for improvements that would benefit the original project, rather than only maintaining them privately in your fork.

Failing to provide the required attribution when distributing a fork or derivative work is a violation of the project license.

## Reporting bugs & requesting features

Please open an issue on the repository's issue tracker and include:

- A clear description of the problem or request.
- Steps to reproduce (for bugs), including relevant config snippets (redact secrets!).
- Expected vs. actual behavior.
- Environment details (OS, Python version, whether running via `uv run` or Docker Compose).

## Attribution requirement

This project is distributed under a **MIT License with an Attribution Requirement** (see [LICENSE](LICENSE)). In short: you're free to use, modify, and distribute Agentic (including in forks and derivative products), but you must credit the original author, **Mayank Shinde**, and the original **Agentic** project wherever the software or a derivative of it is used or distributed. Please read the [LICENSE](LICENSE) file for the full terms.

Thank you for helping make Agentic better! 🎉

