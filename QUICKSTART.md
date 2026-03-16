# terminal-hub Quickstart

> terminal-hub lets Claude Code create GitHub issues, track project context, and remember your project setup — all from inside a conversation.

---

## Before you start

You need:
- **Python 3.10+** — check with `python3 --version`
- **Claude Code** — check with `claude --version`
- **A GitHub account** (optional — local-only mode works without one)

---

## Step 1 — Install the package

```bash
pip install terminal-hub
```

This makes the `terminal-hub` command available and installs the MCP server.

> On some systems you may need `pip3` instead of `pip`.

---

## Step 2 — Register with Claude Code

```bash
terminal-hub install
```

You'll see a preview of what gets written to `~/.claude.json`, then a confirmation prompt. Type `y`.

```
Will add to ~/.claude.json (global):
  mcpServers["terminal-hub"] = { ... }

Write this config? [y/N] y
✓ Written to /Users/you/.claude.json
✓ Restart Claude Code to apply changes.
```

> This registers the MCP server globally — you only do this **once**.

---

## Step 3 — Restart Claude Code

Close and reopen Claude Code. It reads `~/.claude.json` on startup.

---

## Step 4 — Install the plugin (inside Claude Code)

Run this inside a Claude Code conversation:

```
/plugin install terminal-hub
```

This installs the workflow agents and hooks — the prompts that guide Claude through issue creation, project context, and auth recovery automatically.

---

## Step 5 — Open a project and start

Navigate to your project and open Claude Code:

```bash
cd my-project
claude
```

Then just say: **"Set up terminal-hub for this project"**

Claude will ask if you want GitHub integration, set up a `hub_agents/` folder, and be ready to go.

---

## What you can do

| Say to Claude | What happens |
|---------------|-------------|
| "Create an issue for the login bug" | Creates a GitHub issue + saves it locally |
| "What are we tracking?" | Lists all issues |
| "Save a description of this project" | Writes to `hub_agents/project_description.md` |
| "What architecture did we decide on?" | Reads back saved notes |

---

## Verify at any time

```bash
terminal-hub verify
```

```
✓ terminal-hub is configured globally.
```

---

## Troubleshooting

**Claude doesn't see terminal-hub tools**
→ Did you restart Claude Code after `terminal-hub install`?

**`terminal-hub` command not found**
→ Run `pip install terminal-hub` first. If it still fails, check that pip's bin directory is in your `PATH`.

**GitHub calls fail**
→ Run `gh auth login` in your terminal, then tell Claude "I've logged in". No `gh`? Set `GITHUB_TOKEN=<token>` in your environment instead.

**"No GitHub repo configured"**
→ Ask Claude: "Set up terminal-hub for this project" and provide your repo as `owner/repo-name`.

---

## Developer install (contributors)

```bash
git clone https://github.com/JuneKim0007/terminal_hub.git
cd terminal_hub
pip install -e .         # editable install — code changes take effect immediately
terminal-hub install
```
