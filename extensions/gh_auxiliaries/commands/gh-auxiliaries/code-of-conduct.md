<!-- LOAD ANNOUNCEMENT: At the very start of this command, output exactly:
     🟢 Loaded: gh-auxiliaries/code-of-conduct — `extensions/gh_auxiliaries/commands/gh-auxiliaries/code-of-conduct.md`
     Do this before any tool calls. -->

<!-- RULE: WORKSPACE ROOT — always call set_project_root(path=<cwd>) as the very first tool call. -->

<!-- RULE: Never auto-generate CODE_OF_CONDUCT.md. Every step requires explicit user
     confirmation before proceeding to the next. -->

<!-- RULE: Templates b and c must be followed verbatim — do not paraphrase or restructure.
     Inject metadata only into explicit placeholders. -->

<!-- RULE: Save extracted metadata to hub_agents/community.json after user confirms it.
     This cache is shared across all th:gh-auxiliaries sub-commands. -->

<!-- NOTE: Full implementation is tracked in GitHub issue #201.
     This stub exists so the command installs and routes correctly. -->

You are in **gh-auxiliaries/code-of-conduct** mode.

_This generator is under active development (GitHub issue #201 — M4: GitHub Community Standards)._

**Current status:** stub — command routing works, implementation pending.

When this command is fully implemented it will:

1. Scan config files (`pyproject.toml`, `package.json`, `.github/CODEOWNERS`, `LICENSE`, `README.md`) for project metadata
2. Present findings and let you override any field
3. Ask which Code of Conduct template to use (default: Contributor Covenant v2.1)
4. Show a full draft for review with edit-sections / start-over options
5. Write `CODE_OF_CONDUCT.md` to the project root and optionally link it from README/CONTRIBUTING.md

To follow progress or contribute, see: https://github.com/JuneKim0007/terminal_hub/issues/201
