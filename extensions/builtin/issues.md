# terminal-hub: Issue Browser

When this command is loaded, call `list_issues` immediately and render the results as an interactive indexed list.

## Step 1 — Render the list

Call `list_issues`. Then display:

```
Issues (N)
──────────────────────────────────────
[1]  #<num>  <title>
[2]  #<num>  <title>
...
──────────────────────────────────────
▶ Type a number (1–N) to expand, or anything else to exit.
```

Rules:
- Show at most 9 issues per page (single-digit input is unambiguous)
- If more than 9 issues exist, show `▶ next` as a final option
- If `issue_number` is absent, show `local` instead of `#N`
- After rendering, append this hidden state block (do NOT omit it):
  `<!-- navigation: active | index: {"1": "<slug1>", "2": "<slug2>", ...} -->`

## Step 2 — Handle user input

On the user's next reply:

| Input | Action |
|-------|--------|
| `1`–`9` | Expand that issue (Step 3) |
| Same number as currently expanded | Collapse it, re-render list |
| `next` | Show next page of 9 |
| `q` or any other text | Exit navigation mode (Step 4) |

If the hidden state block is missing (e.g. context was compacted), re-call `list_issues` and rebuild the list from scratch before handling input.

## Step 3 — Expand an issue

Call `get_issue_context(slug)` for the selected slug from the state block. Render the expanded view inline, replacing that row:

```
[1]  #<num>  <title>
     Status:   <status>
     Created:  <created_at>       ← omit if None
     Assignees: <a>, <b>          ← omit if empty
     Labels:   <label>, <label>   ← omit if empty
     URL:      <github_url>       ← omit if None
     File:     <file>
```

Re-render the full list with this issue expanded. Re-append the hidden state block. Prompt again:
`▶ Type a number to expand another, or anything else to exit.`

## Step 4 — Exit navigation mode

When user types anything non-navigational, respond:
```
Exiting issue browser. (Treating your message as a new request.)
```
Then handle their message normally.
