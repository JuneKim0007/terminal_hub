# Installation

Install terminal-hub and register it with Claude Code.

---

## Requirements

- Python 3.10+
- [Claude Code](https://claude.ai/code)
- GitHub CLI (`gh`) — optional, needed for GitHub mode

---

## Install

```bash
pip install terminal-hub
terminal-hub install
```

`terminal-hub install` registers the MCP server in `~/.claude.json` and copies all slash command `.md` files to `~/.claude/commands/th/`. Run this once, or after every upgrade.

**Verify:**

```bash
terminal-hub verify
```

Checks that terminal-hub is registered in `~/.claude.json`. If verification fails, re-run `terminal-hub install`.

**Then restart Claude Code.** The MCP server starts alongside Claude Code and all `/th:` commands become available.

---

## GitHub mode (optional)

Without any configuration, terminal-hub runs in **local-only mode** — issues are tracked as local `.md` files and no GitHub API is used.

To enable GitHub mode, set two values in `hub_agents/.env` (created on first run):

```
GITHUB_TOKEN=ghp_...
GITHUB_REPO=owner/repo
```

| Variable | Required | Where to set | Description |
|----------|----------|--------------|-------------|
| `GITHUB_TOKEN` | GitHub mode only | `hub_agents/.env` or shell | PAT with `repo` scope. Not needed if you use `gh auth login`. |
| `GITHUB_REPO` | GitHub mode only | `hub_agents/.env` or shell | Target repo in `owner/repo` format (e.g. `alice/my-project`) |

**Recommended — use `gh` CLI auth:**

```bash
gh auth login
```

terminal-hub detects your `gh` session automatically — no `GITHUB_TOKEN` needed.

---

## Docker

```dockerfile
FROM python:3.11-slim
RUN pip install terminal-hub
RUN terminal-hub install
```

Full compatibility across all environments cannot be guaranteed.

---

## Upgrading

```bash
pip install --upgrade terminal-hub
terminal-hub install   # re-installs slash commands
```

Always re-run `terminal-hub install` after upgrading to pick up new commands.

---

## Troubleshooting

**Commands not appearing:**
- Run `terminal-terminal verify`
- Check `~/.claude/commands/th/` contains `.md` files
- Restart Claude Code

**MCP server not found:**
- Check `~/.claude.json` has a `terminal-hub` entry under `mcpServers`
- Re-run `terminal-hub install`

**GitHub auth errors:**
- Run `gh auth login` and retry
- Or set `GITHUB_TOKEN` in `hub_agents/.env`
- Use `/th:gh-plan-auth` in Claude Code for guided recovery
