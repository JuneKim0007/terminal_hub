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
   > "What are you building? Give me a quick overview — what it does, any tech stack in mind, and roughly how big."

3. From the answer, infer a project name and one-line goal. Show before saving:
   > "Got it — here's what I have:
   > **Name:** <inferred-name>
   > **Goal:** <one-line description>
   > Correct? (yes / tweak it)"
   Wait for confirmation before proceeding.

4. Ask:
   > "Keep it local, or push to GitHub too? (local / github)"
   - **local** → call `setup_workspace(project_root=<cwd>)`
   - **github** → ask "Use an existing repo (`owner/repo`) or create a new one? (existing / new)"
     - **existing** → call `setup_workspace(project_root=<cwd>, github_repo=<owner/repo>)`
     - **new** → call `create_github_repo(name=<inferred-name>, description=<goal>, private=true)`,
       then `setup_workspace(project_root=<cwd>, github_repo=<owner/repo>)`

5. Ask about project documentation:
   > "How should I learn about your project?
   > a) Analyze the repo — I'll scan your files and generate project notes
   > b) You have existing docs — connect them as references
   > c) Start fresh — I'll ask you some questions"

   - (a): Switch to /th:gh-plan-analyze
   - (b): Connect existing docs — call `search_project_docs()` to find candidates, show the list,
     ask user to pick primary (always-loaded into planning context) and any others (loaded on demand
     by section), then call `connect_docs(primary={path, description}, others=[...])`
   - (c): Follow /th:gh-plan new-repo path (Step 2 project description flow)

6. Confirm: "You're set up! Run /th:gh-plan to start planning issues."

7. Call `apply_unload_policy(command="init")` and print `_display` verbatim.
