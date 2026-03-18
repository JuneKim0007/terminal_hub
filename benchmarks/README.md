# Benchmarks

Compare token usage between vanilla Claude Code and Claude Code with terminal-hub.

## Structure

```
benchmarks/
├── project.md                  # Shared input: calculator project spec
├── vanilla/
│   └── PROMPT.md               # Prompt + instructions for vanilla run
├── with-terminal-hub/
│   └── PROMPT.md               # Prompt + instructions for terminal-hub run
└── results/                    # Gitignored — fill in after each run
    ├── vanilla.json
    └── with-terminal-hub.json
```

## Running a benchmark

1. Follow the instructions in `vanilla/PROMPT.md` — run in a fresh Claude Code session with NO terminal-hub
2. Follow the instructions in `with-terminal-hub/PROMPT.md` — run in a fresh Claude Code session WITH terminal-hub MCP active
3. Record token counts and tool calls in `results/`

## Task

Both sessions receive the same prompt:
> "Read project.md and make a public GitHub repo for this project. Set up the calculator app described there. Create GitHub issues for each feature."

Both sessions have access to the same `project.md` describing a simple calculator (add, sub, mul).

## Metrics

| Metric | What it measures |
|--------|-----------------|
| `input_tokens` | Context loaded by the model |
| `output_tokens` | Tokens generated |
| `tool_calls` | How many tools were invoked |
| `github_issues_created` | Did it create the right issues? |
| `repo_created` | Was the GitHub repo created? |
