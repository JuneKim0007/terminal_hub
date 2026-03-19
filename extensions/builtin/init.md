# /th:init — Project Bootstrap

<!-- LOAD ANNOUNCEMENT: output exactly:
     🟢 Loaded: th:init — `extensions/builtin/init.md`
     before any tool calls -->

Bootstrap a new project with terminal-hub workspace setup.

## Steps

1. Call `get_setup_status(project_root=<Claude's cwd>)` to check if already initialised
   - If initialised: "Already set up. Run /th:gh-plan to start planning."
   - If not: continue

2. Ask conversationally:
   > "Let's set up your project. Do you have a GitHub repo connected already, or should I help you create one?"
   > a) Yes, here's the repo: `owner/repo`
   > b) Create one for me
   > c) Skip — work locally for now

3. Call `setup_workspace(project_root=<cwd>, github_repo=<if provided>)`

4. Ask about project documentation:
   > "How should I learn about your project?
   > a) Analyze the repo — I'll scan your files and generate project notes
   > b) You have existing docs — connect them as references
   > c) Start fresh — I'll ask you some questions"

   - (a): Switch to /th:gh-plan-analyze
   - (b): Connect existing docs — call `search_project_docs()` to find candidates, show the list,
     ask user to pick primary (always-loaded into planning context) and any others (loaded on demand
     by section), then call `connect_docs(primary={path, description}, others=[...])`
   - (c): Follow /th:gh-plan new-repo path (Step 2 project description flow)

5. Confirm: "You're set up! Run /th:gh-plan to start planning issues."

6. Call `apply_unload_policy(command="init")` and print `_display` verbatim.
