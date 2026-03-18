# With terminal-hub — Benchmark Prompt

**Scenario**: terminal-hub MCP server active in Claude Code.

## Setup

1. Start a fresh Claude Code session with terminal-hub MCP enabled
2. Copy `../project.md` into the session directory as `project.md`
3. Use this prompt:

---

> Read project.md and make a public GitHub repo for this project.
> Set up the calculator app described there. Create GitHub issues for each feature.

---

## What to record

After the session ends, fill in `../results/with-terminal-hub.json`:

```json
{
  "input_tokens": 0,
  "output_tokens": 0,
  "tool_calls": 0,
  "github_issues_created": 0,
  "repo_created": true,
  "notes": ""
}
```

You can find token counts in the Claude Code session stats (`/cost` command or session log).
