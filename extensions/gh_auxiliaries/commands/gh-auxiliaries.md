<!-- LOAD ANNOUNCEMENT: At the very start of this command, output exactly:
     🟢 Loaded: gh-auxiliaries — `extensions/gh_auxiliaries/commands/gh-auxiliaries.md`
     Do this before any tool calls. -->

<!-- RULE: WORKSPACE ROOT — always call set_project_root(path=<cwd>) as the very first tool call. -->

<!-- RULE: Never auto-generate any community file. Only proceed when the user explicitly
     selects a sub-command. Coming-soon items must be labelled clearly — do not attempt
     to implement them. -->

<!-- RULE: for every yes/no or choice prompt shown to the user, call
     format_prompt(question, options, style) first and print _display verbatim. -->

You are in **gh-auxiliaries** mode — the community standards generator for your project.
Each sub-command generates a specific GitHub community file on demand.

---

## Step 1 — Workspace (silent)

Call `set_project_root(path="<Claude's actual working directory>")`.

---

## Step 2 — Sub-command menu

Show the following menu verbatim:

```
th:gh-auxiliaries — Community Standards Generator

  a) Code of Conduct   → /th:gh-auxiliaries/code-of-conduct
  b) Security Policy   (coming soon — M4)
  c) Issue Templates   (coming soon — M4)
  d) PR Template       (coming soon — M4)

Which would you like to generate? (a / b / c / d)
```

- **(a)** → load and follow `extensions/gh_auxiliaries/commands/gh-auxiliaries/code-of-conduct.md`
- **(b / c / d)** → respond:
  > "That generator is not yet available — it's planned for M4 (GitHub Community Standards).
  > You can track progress at https://github.com/JuneKim0007/terminal_hub/issues"
  Then offer to return to the menu or exit.

---

## Sub-commands

| Command | Does |
|---------|------|
| `/th:gh-auxiliaries/code-of-conduct` | Generate `CODE_OF_CONDUCT.md` with template selection and metadata injection |
