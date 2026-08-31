# Refactor backlog

Surveyed 2026-08-31 · scope `terminal_hub/` + `extensions/` · 53 files
Baseline: tests 1074 green · 9,672 lines · 237 comment lines · 126 commits of history

Ids are permanent. Never renumber, never reuse a retired id. Next id: **R21**.

This file is written by `/refactor-facade` and reconciled by it. Do not mark items
closed by hand — re-run the survey after a stretch of work and let it find them.

---

## Open

### R4 · Duplicate code · 34 sites across 7 files · workspace guard preamble
```
status   blocked — awaiting user answer
evidence the 3-line opening `_p = _pkg(); root = _p.get_workspace_root();
         if err := _p.ensure_initialized(root): return err` occurs 34 times —
         labels ×7, issues ×7, project_docs ×6, workspace_tools ×6,
         milestones ×5, gh_implementation ×2, analysis ×1
remedy   Extract Method -> refactor-composing-method
expect   −68…−102 lines
blocked  safety gate returned ASK (34 call sites, threshold 20). Question put
         to the user 2026-08-31: decorator / plain helper / leave.
         Recommended: plain helper, so the ~600-patch-site indirection stays
         visible at the call site instead of hiding inside a decorator.
first seen 2026-08-31
```

### R6 · Shotgun surgery · tool wrapper + implementation + command docs + json
```
status   blocked — awaiting user answer
evidence one concept (a tool) spans 4 artefacts. Co-occurrence over 126 commits:
         __init__+commands 19x · +storage 7x · +client 7x · +plugin.json 6x ·
         +unload_policy.json 5x. 8 commits touch wrapper AND domain module AND
         command doc together.
remedy   Move Method -> refactor-moving-feats-btw-objects
expect   a tool change lands in 1 file instead of 2
blocked  safety gate returned ASK (62 tools relocate, crosses module
         boundaries). Recommended: move 2 domains (labels, milestones) as a
         trial, re-survey, then decide the other 9.
depends  R5 (done) — the registrars must exist before they can move
first seen 2026-08-31
```

### R7 · Long parameter list · storage.py:104 · write_issue_file
```
status   blocked — awaiting user answer
evidence 17 named parameters, 7 required. 10 of them (title, status, created_at,
         assignees, labels, workflow, agent_workflow, note, milestone_number,
         milestone_title) are assigned straight into one `frontmatter` dict and
         never read individually.
remedy   Introduce Parameter Object -> refactor-simplifying-method
expect   17 params -> 4 + one IssueFrontmatter
blocked  safety gate returned ASK (46 call sites). Recommended: apply.
first seen 2026-08-31
```

### R8 · Long method · 5 remaining sites · the _do_* cluster
```
status   blocked — the 3 with adequate coverage are done; these 5 are not
         provable yet
evidence runtime_state.py:24 get_runtime_state 77 stmts/d4 ·
         issues.py:551 _do_sync_github_issues 72/d3 ·
         workspace_tools.py:429 _do_apply_unload_policy 71/d4 ·
         labels.py:54 _do_analyze_github_labels 67/d3 ·
         analysis.py:430 _do_analyze_repo_full 66/d4 ·
         milestones.py:326 _do_generate_milestone_knowledge 65/d1 ·
         issues.py:372 _do_generate_issue_workflows 59/d5 ·
         issues.py:20 _extract_design_refs 39/d5 + control flag `in_principles`
remedy   Extract Method, Remove Control Flag -> refactor-composing-method
expect   no body over 40 statements
blocked  per-function coverage measured 2026-09-01. check-safety-refactoring
         step 2 refuses a refactor whose preservation cannot be proved, and
         these five sit below the line:
           get_runtime_state                83.8%  (13 lines unhit)
           _do_sync_github_issues           94.6%  (4)
           _do_generate_milestone_knowledge 78.5%  (14)
           _do_generate_issue_workflows     91.5%  (5)
           _extract_design_refs             84.6%  (6)
         Characterisation tests for the unhit lines come first, in their own
         commit — see R21. The three that were >=95% are closed below.
first seen 2026-08-31
```

### R21 · Tests · characterisation coverage for the R8 remainder
```
status   planned
evidence the 5 functions above have 42 unhit lines between them. They are the
         gate on R8, not optional polish.
remedy   add tests covering the listed lines, then return to R8
expect   all 5 above 95%, R8 unblocked
blocked  none
first seen 2026-09-01
```

### R9 · Data clumps · 5 groups × 3 sites
```
status   planned
evidence (name,color,description) __init__/labels/client ·
         (title,description,due_on) __init__/milestones/client ·
         (feature_name,overview,milestone,guidelines,anti_patterns) ×3 ·
         (title,description,notes) ×3 · (overview,components,notes) ×3.
         Deletion test passes on all five.
remedy   Introduce Parameter Object -> refactor-simplifying-method
expect   5 groups -> 5 value types; the MCP wrapper keeps flat params (wire)
blocked  interacts with R6 — decide the wrapper location first
first seen 2026-08-31
```

### R16 · Inappropriate intimacy · terminal_hub/server/__init__.py · residual host→plugin dependency
```
status   planned
evidence after R1/R2 the host still imports 3 names from the plugin —
         ensure_initialized, get_github_client, _invalidate_repo_cache — read
         via `_srv.<name>` by tools.setup, tools.runtime_state,
         tools.plugin_registry. These are genuine plugin functions, not
         aliases, so the cycle is narrowed (8 names / 2 blocks -> 3 / 1) and
         not closed. ensure_initialized only checks `(root/"hub_agents")
         .exists()` — hub_agents/ is terminal-hub's own directory, so this
         looks like core policy living in a plugin.
remedy   Move Method into terminal_hub.workspace -> refactor-moving-feats-btw-objects
expect   terminal_hub stops naming any plugin
blocked  33 tests patch ...github_planner.ensure_initialized; needs its own
         safety pass
first seen 2026-08-31
```

### R17 · Duplicate setup · 207 sites · create_server() with no fixture
```
status   blocked — needs a safety pass
evidence create_server() is called 207 times across the suite with no shared
         fixture. Measured 29.1ms each = 6.0s of what was a 14s suite. The cost
         is not discovery (0.3ms) or instruction building (0.0ms) but
         registering 66 tools into FastMCP — 99% of it — so it cannot be cached
         without sharing the instance itself.
remedy   pytest fixture -> (test infrastructure, no refactor skill)
expect   -6.0s suite time
blocked  create_server() calls _state.reset(), and test_server_internals.py and
         tools/test_plugin_registry.py assert on _PLUGIN_WARNINGS /
         _LOADED_EXTENSIONS. Mixing a shared server with fresh ones creates
         order-dependent tests — a worse defect than the 6s it saves. Needs a
         scoped design (session fixture + explicit opt-out) and proof of
         order-independence before it is schedulable.
first seen 2026-08-31
```

### R18 · Tests · zero-unique-coverage files
```
status   planned
evidence per-file unique line coverage measured across 56 test files, with the
         427-line import-time baseline subtracted. Files adding zero unique
         line coverage: tools/test_list_issues.py (real 544),
         tools/test_setup_status_existing.py (516), test_config.py (22),
         test_slugify.py (8). test_plugin_customization.py was in this set and
         is now closed.
remedy   inspect each for behaviourally-unique assertions, then merge or delete
expect   fewer tests, same coverage
blocked  none — but see the note below: zero unique LINE coverage is not proof
         of redundancy. 2 of the 9 tests in the file closed this run were
         behaviourally unique despite contributing no unique lines.
first seen 2026-08-31
```

### R19 · Tests · contract-shaped assertions
```
status   planned
evidence 256 `assert "x" in y` key-presence assertions and 65 `_display`
         assertions across the suite. These pin response *shape* rather than
         behaviour, so they duplicate what the MCP schema already declares.
remedy   judgement call per site — not a mechanical sweep
expect   unknown; measure before acting
blocked  none, but low value. The _display assertions in particular are the
         only check that user-facing strings render, so they are not obviously
         waste. Do not sweep this without a per-site read.
first seen 2026-08-31
```

---

## Done

### R8a · Long method · 3 of 8 sites (the ones coverage could prove)
```
closed 2026-09-01 — refactored the three targets at >=95% line coverage:
  _do_analyze_github_labels  67 -> 33 stmts  (labels.py, was 98.6% covered)
  _do_analyze_repo_full      66 -> 28 stmts  (analysis.py, 95.6%)
  _do_apply_unload_policy    71 -> 41 stmts  (workspace_tools.py, 95.8%)
Extracted _label_names_with_open_issues, _label_age_days, _classify_labels,
_persist_label_analysis, _make_profile_filter, _partition_tree,
_fetch_file_index, _clear_caches, _render_unload_lines, _render_keep_lines.
Coverage 89.70% -> 89.72%; 1067 tests green throughout.
_do_apply_unload_policy is 41 stmts, one over the threshold — the remainder is
a flat result-assembly block with no reusable group, which the bloaters skill
excludes explicitly.
```

### R22 · Duplicate code · workspace_tools.py · _CACHE_KEY_MAP defined twice
```
closed 2026-09-01 — the 15-entry cache-key map and its 6 imports were spelled
out byte-identically in _load_unload_policy (line 52) and
_do_apply_unload_policy (line 444) of the same file. Found by accident: a
regex written to match one of them spanned both and broke the module. Now one
_cache_key_map() serving both. -24 lines.
Missed by the original sweep because 6-statement window hashing found it only
as a single collision inside one file, which ranked below the cross-file
findings and was never read.
```

### R20 · Bug · tests/tools/test_setup_workspace.py:45 · live network call
```
closed 2026-08-31 — test_setup_with_github_repo patched get_workspace_root but
not get_github_client, so setup_workspace ran gh.ensure_labels() against the
real api.github.com. Proved with a socket guard: a TLS connection to
('20.233.83.146', 443). 5.58s of a 14s suite, and a failure on any machine
without credentials or a route. Client mocked; a permanent autouse network
guard added to tests/conftest.py with a @pytest.mark.network opt-out.
Not a smell — a bug, found during the smell sweep.
```

### R1 · Speculative generality · terminal_hub/server/__init__.py
```
closed 2026-08-31 — 7 re-exports with no reader deleted (write_issue_file,
write_doc_file, resolve_token, verify_gh_cli_auth, build_instructions,
discover_plugins, load_plugin); the whole github_planner.storage import block
went with them. 18 names -> 11. Docstring corrected: it claimed to re-export
"the entire historical surface area" for test patching, a reason true for 7 of
the 18.
```

### R2 · Middle man · github_planner/setup.py:35 · get_workspace_root
```
closed 2026-08-31 — the host now does
`from terminal_hub.workspace import resolve_workspace_root as get_workspace_root`.
get_workspace_root was a 2-line forward to that function, so the core was
importing a plugin to obtain something that called back into the core. The
patch target `terminal_hub.server.get_workspace_root` (65 sites) is preserved.
```

### R3 · Duplicate code · _pkg() × 9 modules
```
closed 2026-08-31 — one definition in github_planner/pkgref.py, imported by 9
modules. The indirection is deliberate and was preserved: `from … import f`
binds at import time, which would silently defeat ~600 test patch sites. The
reason is now stated once instead of copied nine times.
```

### R5 · Long method · github_planner/__init__.py:184 · register
```
closed 2026-08-31 — 202 statements -> 12, split into 11 _register_*(mcp)
functions along the section comments that were already there; each banner
became the function name and docstring. Verified: 66 registered callables
before and after with identical names, decorators, signatures and docstrings.
```

### R10 · Message chains · 5 sites · repo-root Path chains
```
closed 2026-08-31 — terminal_hub/config/paths.py defines PACKAGE_ROOT,
REPO_ROOT, EXTENSIONS_DIR, BUILTIN_COMMANDS_DIR once, exported through the
config facade. Two sites previously disagreed on the parent count (3 vs 4) for
the same directory because the count depended on the caller's package depth.
```

### R12 · Switch statements · plugin_customization/__init__.py:156 · task_type
```
closed 2026-08-31 — the 3-arm if/elif became _RESULT_PROMOTIONS, joining the
two lookup tables already keyed by task_type in the same file.
```

### R18a · Duplicate code · test_plugin_customization.py
```
closed 2026-08-31 — the file duplicated tools/test_dispatch_task.py near
verbatim (test_file_location_returns_files_key vs
test_file_location_promotes_files_key, and 4 more pairs). test_dispatch_task.py
alone reaches 100% of plugin_customization. 2 of the 9 tests were
behaviourally unique — they exercise _model_for_task directly with a known vs
an unknown key — and were merged rather than deleted; the other 7 were removed.
Coverage before and after: 112 statements, 0 missed, 100%.
```

### R13 · Dead code · 2 definitions
```
closed 2026-08-31 — labels.py _get_cached_label_names and storage.py
STATUS_CLOSED, each with exactly one reference in the repo: its own definition.
```

---

## Dropped

### R14 · Comments · 63 section banners
```
dropped 2026-08-31 — 2.7% comment ratio overall (tokenized, not regexed) is
already low. 11 of the 63 were absorbed by R5, where each banner became a
function name. The rest sit over constant tables and are that table's only
structure.
```

### R11 · Primitive obsession · gh_auxiliaries/__init__.py:281 · template_key
```
dropped 2026-08-31 as specified — template_key is a parameter on the
generate_and_write_coc MCP tool, so its type is part of the schema the model
reads. Converting it to an Enum crosses the wire; the safety gate refuses that
at check 1. Smaller change recorded instead: keep str at the boundary, convert
internally after the membership check, and collapse _TEMPLATE_URLS and
_TEMPLATE_NAMES into one table. Not scheduled — the finding is cosmetic once
the wire is off the table.
```

### R15 · Primitive obsession · slug
```
dropped 2026-08-31 — validate_slug is called at 10 sites, which is a real
signal, but the slug IS the on-disk filename (hub_agents/issues/{slug}.md) and
a YAML frontmatter key. A value-object conversion crosses a stored format; the
safety gate refuses that at check 1. The validator at 10 sites is the correct
shape for a value whose format is owned by the filesystem.
```

---

## Refused

### GitHubClient · Large class
```
refused — 18 public methods and 292 lines clear the count thresholds, but
cluster analysis rejects it: _client is touched by 19 methods, repo by 11, and
every repo method also touches _client. One cluster, not two. Extract Class
would split a cohesive client along an axis that does not exist.
```

### github_planner/__init__.py · Divergent change
```
refused — 54 commits in 8 unrelated subject clusters, 3x the threshold. But
issue #214 already performed the Extract Class this smell prescribes; the
implementations live in issues/milestones/labels/project_docs/analysis/
skills/workspace_tools. What remains is a registry, and listing unrelated
things is a registry's job. The residual pain is R6, not this.
```

### github_planner/__init__.py · Middle man (62 tool wrappers)
```
refused — the forwarding ratio is ~100%, but the docstring IS the MCP tool
schema. FastMCP reads the signature and docstring to build the wire contract;
draft_issue's 40-line docstring is user-facing API documentation. Inlining the
wrappers would delete the protocol surface. An adapter across a real boundary.
```

---

## Notes for the next survey

Static analysis under-reports usage in this codebase. Names are reached three
ways — `from X import Y`, `X.Y`, and `import X as _x` then `_x.Y` — and tests
patch module attributes, so ruff's F401 and any grep for unused re-exports will
both produce false positives. Three were caught this run only by running the
suite (`_assert_builtins`, `plugin_registry.Path`, and the `_srv.` readers that
made the original "36 of 53 unused" count wrong; the true figure was 7 of 18 on
the server facade). Treat the suite as the detector, not the linter.
