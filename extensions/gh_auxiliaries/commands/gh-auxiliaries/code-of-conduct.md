<!-- LOAD ANNOUNCEMENT: At the very start of this command, output exactly:
     🟢 Loaded: gh-auxiliaries/code-of-conduct — `extensions/gh_auxiliaries/commands/gh-auxiliaries/code-of-conduct.md`
     Do this before any tool calls. -->

<!-- RULE: WORKSPACE ROOT — call set_project_root(path=<cwd>) as the very first tool call. -->

<!-- RULE: Never auto-generate CODE_OF_CONDUCT.md. Every step requires explicit user
     confirmation before proceeding to the next. -->

<!-- RULE: generate_and_write_coc() is the ONLY tool that writes the CoC file.
     Never call write_community_file() with CoC template text — that triggers content filters.
     Template content is fetched and written server-side, entirely in Python. -->

<!-- RULE: Save confirmed metadata to community.json via save_community_metadata() before
     calling generate_and_write_coc(). This cache is shared across all th:gh-auxiliaries calls. -->

You are in **gh-auxiliaries/code-of-conduct** mode — the Code of Conduct generator.

---

## Step 1 — Workspace (silent)

Call `set_project_root(path="<Claude's actual working directory>")`.

---

## Step 2 — Scan metadata (silent)

Call `scan_community_metadata()`.

Present the findings to the user exactly like this:

```
Found in <source>:
  Project name:  <project_name or "not found">
  Maintainer:    <maintainer_name or "not found">
  Contact:       <contact_email or "not found">
  Enforcement:   <enforcement_contact — defaults to contact_email>
Use these? (yes / edit)
```

- **yes** → call `save_community_metadata(...)` with confirmed values, proceed to Step 3
- **edit** → ask which fields to change, collect new values, then `save_community_metadata(...)`, proceed to Step 3
- If no metadata was found → ask the user to provide project_name, contact_email manually, then `save_community_metadata(...)`, proceed to Step 3

---

## Step 3 — Template selection

Call `format_prompt` then show:

```
Which Code of Conduct template?
  a) Contributor Covenant v2.1  [default] — used by 40,000+ open source projects
  b) Django Code of Conduct     — includes a detailed enforcement manual
  c) Citizen Code of Conduct    — broader community focus
  d) Write my own               — you describe your values, I draft a custom document

(press Enter / say "default" to use option a)
```

- **a / Enter / "default" / skip** → proceed to Step 4 with `template_key="a"`
- **b** → proceed to Step 4 with `template_key="b"`
- **c** → proceed to Step 4 with `template_key="c"`
- **d** → go to Step 3d (custom flow)

### Step 3d — Custom CoC

Ask the user 3 short questions (one at a time):
1. "What behaviours do you want to encourage in your community?"
2. "What behaviours are not acceptable?"
3. "How should violations be reported and handled?"

Collect their answers. Confirm: "I'll draft a CoC based on your answers — proceed?"

On yes: assemble the user's answers into a structured document outline (do NOT write full policy language inline — use the answers as section headers with the user's own words). Call `write_community_file(filename="CODE_OF_CONDUCT.md", content=<assembled draft>)` with only the user-provided text.

Skip Step 4 — go directly to Step 5.

---

## Step 4 — Generate and write

Call `generate_and_write_coc(template_key=<key>, project_name=<from metadata>, contact_email=<from metadata>, enforcement_contact=<from metadata>)`.

**Important:** This tool fetches the template and writes the file entirely in Python.
The content never passes through Claude — do not attempt to read or display the file contents.

On success: tell the user:
> "✅ CODE_OF_CONDUCT.md written using <template name>."
> "Want to link it from your README and/or CONTRIBUTING.md? (readme / contributing / both / skip)"

On error (`fetch_failed`): tell the user the network fetch failed and suggest they re-run with internet access, or fall back to option d (custom).

---

## Step 5 — Link

If the user chose to link:
- Call `link_community_file(targets=[<chosen targets>], filename="CODE_OF_CONDUCT.md")`
- Print `_display` verbatim

If skip: proceed to Step 6.

---

## Step 6 — Done

Say:
> "Done! Your CODE_OF_CONDUCT.md is ready. Run `/th:gh-auxiliaries` to generate other community files (Security Policy, Issue Templates, PR Template)."
