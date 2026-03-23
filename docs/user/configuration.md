# Configuration

Environment variables and workspace layout for terminal-hub.

---

## Environment variables

| Variable | Required | Where to set | Description |
|----------|----------|--------------|-------------|
| `GITHUB_TOKEN` | GitHub mode only | `hub_agents/.env` or shell | GitHub Personal Access Token with `repo` scope. Not needed if you use `gh auth login`. |
| `GITHUB_REPO` | GitHub mode only | `hub_agents/.env` or shell | Target repository in `owner/repo` format (e.g. `alice/my-project`) |

**hub_agents/.env** (created by terminal-hub on first run):

```
GITHUB_TOKEN=ghp_...
GITHUB_REPO=alice/my-project
```

---

## Modes

| Mode | What it does | When to use |
|------|-------------|-------------|
| `local` | Issues tracked as local `.md` files only. No GitHub API calls. | Personal projects, no GitHub account, or offline work |
| `github` | Issues synced to GitHub. Requires `GITHUB_REPO` and auth. | Team projects, open source, or when you want GitHub issue tracking |

Set mode in `hub_agents/config.yaml`:

```yaml
mode: github   # or: local
```

terminal-hub sets this during `/th:gh-plan-setup` — you rarely need to edit it manually.

---

## hub_agents/ workspace layout

All terminal-hub state lives in `hub_agents/` in your project root. This directory is gitignored by default.

```
hub_agents/
├── .env                                      # GITHUB_REPO, optional GITHUB_TOKEN
├── config.yaml                               # mode: local|github, preferences
├── github_global_config.json                 # auth method, username (shared across projects)
├── issues/
│   └── <slug>.md                             # one file per tracked issue (YAML front matter + body)
├── skills/                                   # project-level Tier 2 skills (optional)
│   └── SKILLS.md
└── extensions/
    └── gh_planner/
        ├── project_summary.md                # design principles, tech stack (≤500 tokens, loaded every session)
        ├── project_detail.md                 # feature-area design dictionary (loaded section-by-section)
        ├── docs_config.json                  # connected doc paths (primary, detail, skills)
        ├── docs_strategy.json                # how to handle existing project docs on analysis
        ├── file_tree.json                    # repo file tree cache (TTL: 1 hour)
        ├── analyzer_snapshot.json            # repo analysis cache
        ├── file_hashes.json                  # SHA256 hashes for skip-unchanged optimisation
        └── github_local_config.json          # GitHub labels and repo metadata cache
```

**To start fresh:** delete `hub_agents/` entirely. terminal-hub rebuilds everything on next use.

---

## config.yaml options

```yaml
mode: github                    # local | github
preferences:
  confirm_arch_changes: false   # ask before updating project_detail.md
  milestone_assign: true        # auto-assign issues to milestones
  github_repo_connected: true   # whether a GitHub repo is configured
repo: owner/repo                # active GitHub repo
```

---

## Model routing (plugin_customization)

terminal-hub routes tasks to different Claude models based on weight. Edit `extensions/plugin_customization/plugin_config.json` to customise:

```json
{
  "model_routing": {
    "default": "claude-sonnet-4-6",
    "tasks": {
      "file_location": "claude-haiku-4-5-20251001",
      "classification": "claude-haiku-4-5-20251001",
      "scan": "claude-haiku-4-5-20251001"
    }
  }
}
```

Changes take effect immediately — no server restart needed (hot-reload via mtime check).
