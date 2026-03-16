# terminal-hub Quickstart

> terminal-hub is an MCP server that lets Claude Code create GitHub issues, track project context, and remember your project setup — all from inside a conversation.

---

## Before you start

You need:
- **Python 3.10+** — check with `python3 --version`
- **Claude Code** installed — check with `claude --version`
- **A GitHub account** (optional — you can run in local-only mode without one)

---

## Step 1 — Install terminal-hub

```bash
# Clone the repo
git clone https://github.com/JuneKim0007/terminal_hub.git
cd terminal_hub

# Install it as a package so the terminal-hub command is available
pip install -e .
```

> `-e .` installs in "editable" mode — changes to the code take effect immediately, no reinstall needed.

---

## Step 2 — Register it with Claude Code (one-time, global)

```bash
terminal-hub install
```

You'll see a preview of what will be written to `~/.claude.json`, then a confirmation prompt.

```
Will add to ~/.claude.json (global):
  mcpServers["terminal-hub"] = {
    "command": "/usr/bin/python3",
    "args": ["-m", "terminal_hub"]
  }

Write this config? [y/N] y
✓ Written to /Users/you/.claude.json
✓ Restart Claude Code to apply changes.
```

Type `y` and press Enter.

> This only needs to be done **once**. terminal-hub will be available in every project after this.

---

## Step 3 — Restart Claude Code

Close and reopen Claude Code (or run `claude` again in your terminal).

This is required — Claude Code reads `~/.claude.json` on startup.

---

## Step 4 — Open any project

Navigate to the project directory you want to use terminal-hub with:

```bash
cd /path/to/your-project
claude    # open Claude Code in this directory
```

---

## Step 5 — Let Claude set it up

The first time you use terminal-hub in a project, just tell Claude:

> "Set up terminal-hub for this project"

Claude will:
1. Check if the project is initialised
2. Ask if you want GitHub integration (and for your repo name if yes)
3. Call `setup_workspace` — this creates a `hub_agents/` folder in your project

`hub_agents/` stores all terminal-hub data locally. It is **automatically added to `.gitignore`** so it is never committed.

---

## Step 6 — GitHub auth (if using GitHub integration)

If you said yes to GitHub, Claude will check your auth status. If you're not logged in:

```bash
# Run this in your terminal (not inside Claude)
gh auth login
```

Follow the prompts, then tell Claude: **"I've logged in"** — it will verify and continue.

> Don't have `gh`? Install it from https://cli.github.com or set `GITHUB_TOKEN=<your_token>` in your environment instead.

---

## You're ready

From here, just talk to Claude naturally:

| What you say | What Claude does |
|---|---|
| "Create an issue for the login bug" | Creates a GitHub issue + saves it locally |
| "What issues are we tracking?" | Lists all tracked issues |
| "Save a description of this project" | Writes to `hub_agents/project_description.md` |
| "What was the architecture we decided on?" | Reads back saved architecture notes |

---

## Verify the setup at any time

```bash
# Check that terminal-hub is registered globally
terminal-hub verify
```

```
✓ terminal-hub is configured globally.
{
  "command": "/usr/bin/python3",
  "args": ["-m", "terminal_hub"]
}
```

---

## Troubleshooting

**Claude doesn't seem to know about terminal-hub**
→ Make sure you restarted Claude Code after running `terminal-hub install`

**"No GitHub repo configured"**
→ Ask Claude to run `setup_workspace` again and provide your repo (format: `owner/repo-name`)

**GitHub calls fail with auth errors**
→ Run `gh auth login` in your terminal, then tell Claude "I've logged in"

**`terminal-hub` command not found**
→ Make sure you ran `pip install -e .` from inside the `terminal_hub/` directory
