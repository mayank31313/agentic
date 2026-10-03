# Copilot Instructions for `agentic`

These instructions are used by GitHub Copilot (Chat, code review, and coding
agent) when working in this repository. Follow them in addition to
[`CONTRIBUTING.md`](../CONTRIBUTING.md) and [`architecture.md`](../docs/architecture.md).

## Project context

`agentic` is a config-driven personal AI assistant platform (Python 3.14+,
`uv` for packaging, `deepagents`/LangChain, MCP tool servers, APScheduler,
FastAPI/WebSocket gateway, Telegram channel). Key source lives under
`src/agentic/` (`app/`, `agentic_mcp/`, `cli/`, `websocket_client/`), skills
under `src/skills/`, and runtime wiring in `resources/agentic.json` /
`resources/application.yml`. Tests live under `tests/` and use `pytest`.

## Code review guidelines

When reviewing pull requests or diffs, Copilot should:

1. **Check correctness first.** Verify the change does what the PR/commit
   description claims, and flag logic errors, off-by-one mistakes, unhandled
   exceptions, race conditions (especially around the scheduler, async
   Telegram handlers, and the WebSocket gateway), and resource leaks
   (unclosed files, sessions, DB connections).
2. **Apply core programming principles** and call out violations with a
   concrete suggestion:
   - **DRY** — flag duplicated logic that should be extracted into a shared
     function/module.
   - **SRP / Single Responsibility** — flag functions/classes doing too many
     unrelated things; suggest splitting them.
   - **KISS** — flag unnecessarily complex solutions when a simpler one
     exists.
   - **YAGNI** — flag speculative abstraction/config not needed by the
     current change.
   - **Separation of concerns** — business/agent logic should not be mixed
     with I/O, config parsing, or presentation (CLI/Telegram formatting).
   - **Fail fast / explicit error handling** — avoid silent `except: pass`;
     prefer specific exceptions and meaningful log messages.
   - **Naming & readability** — variables, functions, and classes should be
     descriptive and consistent with existing naming in the module.
3. **Security & secrets.** Never approve code that hardcodes tokens, API
   keys, or credentials. Config-driven secrets should go through
   `resources/application.yml` (`env://VAR_NAME` references), consistent
   with the project's config-first philosophy. Flag anything committed under
   `credentials/` that looks like a real secret.
4. **Config-first consistency.** New tools/integrations belong in
   `src/agentic/agentic_mcp/<tool>/` and should be registered in
   `resources/agentic.json` (`mcpServers`) rather than hardcoded in code, per
   the README's extension guide.
5. **Type hints & style.** Encourage type hints on new/changed public
   functions. Code should pass `ruff check .`; point out lint issues Copilot
   notices even if CI hasn't run yet.
6. **Tests.** New behavior should include or update tests under `tests/`
   (pytest). Bug fixes should include a regression test where feasible. Flag
   PRs that change behavior with no test coverage.
7. **Docs.** If a change affects usage, configuration, or architecture,
   confirm `README.md`, `architecture.md`, or relevant docstrings/skills are
   updated alongside the code.
8. **Be constructive, not just critical.** For every issue raised, propose a
   concrete fix or alternative snippet, not just "this is wrong." Prioritize
   feedback by severity (blocking bug/security issue vs. nit/style).

## Commit message conventions

All commit messages, PR titles, and generated commit summaries **must** use
lightweight [Conventional Commits](https://www.conventionalcommits.org/)
tagging, matching `CONTRIBUTING.md`:

```
<type>: <short, imperative summary>

type ∈ { feat, fix, docs, chore, refactor, test, perf, ci, build, style, revert }
```

Examples:

```
feat: add Slack channel adapter
fix: correct cron schedule parsing for weekly jobs
docs: update README with Vault secrets example
chore: bump deepagents dependency
refactor: extract memory compaction into its own module
test: add coverage for scheduler edge cases
```

When Copilot generates or reviews a commit message / PR title, it should:

- Reject/flag messages that don't start with a valid `type:` prefix.
- Keep the summary line imperative, concise (~50-72 chars), and free of
  trailing punctuation.
- Add a body explaining **why** (not just what) for non-trivial changes.
- Reference related issues using `Closes #123`, `Fixes #123`, or
  `Refs #123` in the body/footer, not the summary line.
- Use a `BREAKING CHANGE:` footer for any change that breaks
  `agentic.json`/`application.yml` schema compatibility or CLI behavior.

## Issues, PRs, and discussion tagging

When drafting or reviewing issues, pull requests, or discussion posts,
ensure they are properly tagged/labeled and cross-referenced:

- **Type label**: one of `bug`, `feature`, `docs`, `chore`, `question`,
  matching the commit `type` taxonomy above.
- **Area label** where applicable: `channel`, `mcp`, `scheduler`, `memory`,
  `gateway`, `cli`, `skills`, `infra` — mirroring the `src/agentic/` module
  layout.
- **Difficulty label** for newcomer-friendly work: `good first issue`,
  `help wanted`.
- **Cross-linking**: PRs must reference the issue(s) they close
  (`Closes #NNN`) or relate to (`Refs #NNN`). Issues opened from a discussion
  should link back to the discussion thread, and vice versa.
- **Bug reports** must include: reproduction steps, expected vs. actual
  behavior, environment (OS, Python version, `uv run` vs. Docker Compose),
  and redacted config snippets — flag reports missing these.
- **Feature requests** must include: the use case/problem being solved, and
  ideally where it fits in the architecture (which module/MCP server/skill).
- **Security-sensitive issues** should not be filed as public issues; note
  this if a report contains credentials/tokens or describes a
  vulnerability, and suggest reporting privately instead.

## Summary for automated review comments

When Copilot leaves an automated review comment, it should:

1. State the principle or convention being violated (e.g. "DRY", "missing
   test", "commit message missing type prefix", "issue missing repro
   steps").
2. Explain the concrete risk/impact.
3. Suggest an actionable fix, ideally as a code suggestion or corrected
   commit/PR text.

