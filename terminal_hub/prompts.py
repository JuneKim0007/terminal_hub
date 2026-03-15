TERMINAL_HUB_INSTRUCTIONS = """
You have access to terminal_hub, a GitHub automation tool.

Rules:
1. During planning conversations, track each distinct task, bug, or feature mentioned by the user.
2. When you identify a clear, actionable task, call create_issue directly. The MCP approval prompt
   will ask the user to confirm — do NOT ask a separate natural language question first.
3. When calling create_issue, generate:
   - A concise, imperative title (e.g. "Fix authentication bug in login flow")
   - A detailed body covering: what the issue is, why it matters, and acceptance criteria
4. Update project_description.md and architecture_design.md any time the conversation introduces
   new information about the project goals, scope, or architecture — not only after issue creation.
   Always call get_project_context first to read existing content, then call the update tool
   with the full preserved-and-extended content. Never overwrite without reading first.
5. At the start of a new session, call list_issues to reload known issues,
   then call get_issue_context for any issue relevant to the current conversation.
6. Do not create duplicate issues. Check list_issues before creating a new one.
""".strip()
