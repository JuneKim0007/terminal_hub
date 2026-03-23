---
name: gh-management-skills
description: Skills registry for gh_management — always loaded on entry. Lists available plugin skills and their load conditions.
alwaysApply: true
---

# gh_management Skills Registry

Always-loaded skills (index only — no heavy knowledge):

| Skill | File | alwaysApply | Load when |
|-------|------|-------------|-----------|
| tools-overview | tools-overview.md | true | Always (tool catalogue) |
| creating-issues | creating-issues.md | false | Drafting, planning, sizing issues |
| milestones | milestones.md | false | Creating milestones, sprint planning |
| implementing | implementing.md | false | Implementing a GitHub issue |
| design-principles | design-principles.md | false | Updating project docs after shipping |
| repo-analysis | repo-analysis.md | false | Running the repo analyzer |
| agent-workflow | agent-workflow-skill.md | false | Writing agent_workflow steps (zero-context rules) |
| workflow | workflow-skill.md | false | Writing ## Workflow body section |
| intent-expansion | intent-expansion-skill.md | false | Expanding vague intent before scanning |
| create-skill | create-skill.md | false | Creating new skill files, skill authoring |
| create-user-readme-docs | create_user_readme_docs.md | false | Writing README.md, user docs, quickstart |
| create-dev-readme-docs | create_dev_readme_docs.md | false | Writing CONTRIBUTING.md, dev docs, plugin authoring |

## Commands (non-skill entry points)

| Command | File | Notes |
|---------|------|-------|
| /th:gh-docs | commands/gh-docs.md | Post-implementation doc writer — create or update README.md + CONTRIBUTING.md, then PR or push. Lives in github_planner (no dedicated extension). |



















Load on demand: `load_skill("name")` — only load when the skill is actually needed.
