# /t-h:github-planner/create-issue

<!-- RULE: after draft_issue or submit_issue, do not narrate the result.
     Continue conversation or say: "Let me know any plans for this!" -->

Guided single-issue workflow:

1. If workspace not initialised, call `get_setup_status` and handle setup first.

2. Ask: "What's the issue? Describe the bug, feature, or task."

3. Listen. Ask one clarifying question if scope is unclear.

4. **Project context lookup** (skip if workspace is brand-new with no docs):
   - Call `docs_exist`. If `summary_exists: false` → skip to step 5.
   - Identify which feature area this issue belongs to from the user's description.
   - Call `lookup_feature_section(feature="{area}")`.
   - If `matched: true`:
     - Use `section` content (Existing Design + Extension Guidelines) as the
       basis for **Acceptance Criteria**.
     - Use `global_rules` to populate a **Constraints** section.
   - If `matched: false`:
     - Silently note `available_features` — do not ask the user about it now.
     - Draft without feature-specific AC; proceed normally.

5. Propose: title (one line, imperative) + body:
   ```
   ## What
   {What the issue is asking for}

   ## Why
   {Context or motivation}

   ## Acceptance Criteria
   - [ ] {Derived from section content if matched, otherwise inferred}

   ## Constraints
   {From global_rules; omit if no docs exist}
   ```

6. Show preview. Ask: "Create this? (yes / edit)"

7. On yes: call `draft_issue(title, body, labels, assignees)`.

8. Before pushing to GitHub, show confirmation block (#82):
   ```
   About to: Create GitHub issue
     Title: "{title}"
     Labels: {labels}
     Repo: {repo}
   Proceed? (yes / save locally only)
   ```
   Wait for explicit "yes" before calling `submit_issue`.

9. If yes: call `submit_issue(slug)`.

10. Say: "Let me know any plans for this!"
