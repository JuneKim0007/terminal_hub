# Refactor backlog

Surveyed 2026-08-31 · scope `terminal_hub/` + `extensions/` · 53 files
Baseline: tests 1074 green · 9,672 lines · 237 comment lines · 126 commits of history

Ids are permanent. Never renumber, never reuse a retired id. Next id: **R27**.

This file is written by `/refactor-facade` and reconciled by it. Do not mark items
closed by hand — re-run the survey after a stretch of work and let it find them.

---

## Open

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

### R9 · Data clumps · 5 groups x 3 sites
```
dropped 2026-09-01 — the original survey counted a tool's wrapper and its
implementation as two independent sites. They are not: the wrapper's signature
IS the MCP schema, so it must mirror the implementation. Re-measured, all 22
repeated signature groups contain a wrapper->impl mirror, and the residual
third member of each x3 group has exactly one call site passing everything
straight through:
  _render_description, _render_architecture, _render_detail_section  1 site each
  create_milestone                                                   1 site
  create_label                                                       3 sites
A parameter object would therefore have one producer and one consumer for four
of the five — Lazy Class, which check-safety-refactoring lists as a fix that
introduces its own smell. The fifth (create_label) has a latent record type in
labels.json, but formalising it crosses a stored format, the same reason R11
and R15 were dropped.
```

### R18 · Tests · zero-unique-coverage files
```
dropped 2026-09-01 — zero unique LINE coverage is not evidence of redundancy in
this codebase, and acting on it would delete real assertions.
test_slugify.py contributes 0 unique lines and is the ONLY file asserting
slugify's behaviour: 10 parametrised cases covering unicode stripping, the
60-char cap and hyphen trimming. It scores zero because slugify is 8 lines that
other tests execute incidentally.
test_config.py is the same shape — 8 focused tests of config save/load and
preferences, all lines touched elsewhere.
The one genuine duplicate this line of enquiry ever found (R18a) was identified
by reading test NAMES, not coverage. Use that method if the question returns.
```

---

## Done

### R26 · Inappropriate intimacy · the host did GitHub work
```
closed 2026-09-01 — three optional plugin hooks in terminal_hub/plugins/hooks.py
(on_workspace_configured, disk_state_items, cache_status), following the
convention register(mcp) already set. github_planner implements all three.
setup_workspace now announces that a workspace was configured instead of
warming a GitHub repo's labels itself; get_runtime_state asks plugins what they
own instead of importing six caches by name.
`grep "from extensions" terminal_hub/` now returns nothing — the host names no
plugin at all.
Observer was justified by a present variation, not a speculative one: 8 plugins
exist, and runtime_state's `except ImportError: pass` already admitted the
dependency should not be there.
Behaviour checked on output, not only on tests: same four item keys in the same
order, same six cache keys.
```

### R6 · Shotgun surgery · tool wrapper vs implementation — complete
```
closed 2026-09-01 — the trial said re-measure before moving the rest. Measured
12 wrappers beside their implementation and 49 not, all 49 with the same clean
one-wrapper-one-_do_ shape. After the move: 61 beside, 0 split. Adding or
changing a tool now touches one file.
Nine _register_* husks left holding only a docstring were removed.
__init__.py 987 -> 416 lines.
Wire surface identical: 66 callables, same names/decorators/signatures/
docstrings; the built server still exposes 91 tools with no load warnings.
Side effect: 23 orphaned package-root re-exports deleted (no consumer by any
access style, suite as detector), and the 108 that remain declared in __all__
instead of looking like dead imports. Lint 100 -> 29.
```

### R16 · Inappropriate intimacy · host importing plugin functions
```
closed 2026-09-01 (partially — see R26) — workspace-initialisation policy moved
to terminal_hub/workspace/init_state.py. The host had been importing
ensure_initialized from a plugin to answer a question about itself: whether
hub_agents/, its own directory addressed by its own terminal-hub:// scheme,
exists. github_planner re-exports the name so ~35 patch sites keep working and
the response text is byte-identical.
Also removed a duplicate: get_setup_status re-implemented the hub_agents/ check
and kept its own copy of the terminal-hub://workflow/init constant. The
condition is now shared; the two messages stay different on purpose, and the
code says why.
server/__init__.py's plugin import: 3 names -> 2.
```

### R25 · Bug · terminal_hub.server._PLUGIN_WARNINGS was a stale binding
```
closed 2026-09-01 — tests/tools/test_plugin_registry.py rebound the attribute
(`srv_mod._PLUGIN_WARNINGS = [...]`) instead of mutating it. server/__init__.py
binds that list at import, so assigning to the name detached the re-export from
state's list for the rest of the session — and the "cleanup" line installed a
third list rather than restoring anything. Later readers saw a stale empty list;
at the failure point the two ids differed and lengths were 0 vs 1.
Fixed in place, plus an autouse guard asserting both buffers are still the state
module's own lists, so the next rebind fails in the test that caused it.
Seeds 7/1/42/99 now all pass. Seed 7 previously failed on unpatched main.
The suite can now be run shuffled; pytest-randomly is deliberately NOT a
dependency — it changes every run, and it is a verification tool.
```

### R23 · Speculative generality · 3 package-root re-exports with no consumer
```
closed 2026-09-01 — _do_assign_milestone, _do_create_milestone and _do_make_label
deleted. Surfaced by the R6 trial, which moved the only wrappers that reached
them. Verified against src, tests, docs and agents: the sole remaining mention
was this backlog's own entry describing them.
```

### R24 · Bug · the test suite overwrote tracked repo files
```
closed 2026-09-01 — four writes went into the plugin's own directory instead of
the workspace: milestone labels into labels.json, created skills and their
registry row into skills/, and source_doc patching into the repo root. All are
tracked, so pytest edited the working tree and one test's result depended on a
file it had itself rewritten. It also meant a reinstall discarded user data and
two projects sharing an install collided.
All four now resolve under the workspace root. A user-created skill is
registered as tier "project", not "plugin" — writing user content into shipped
skill space was the root of it. The project registry is created on demand so
creation still works in a fresh workspace.
No migration needed: nothing read those entries back.
tests/test_install_tree_readonly.py pins the boundary, not the fix.
This destroyed uncommitted local edits repeatedly before the cause was found.
```

### R4 · Duplicate code · the workspace guard preamble
```
closed 2026-09-01 — one _resolve_root() in pkgref.py replaces 33 of 34 copies.
The 2 sites in gh_implementation are deliberately left and now say why: its
tests patch ...gh_implementation.get_workspace_root, its own namespace, so a
helper resolving through github_planner silently bypasses them — attempting it
broke 20 tests. Also removed 15 `_p = _pkg()` bindings the change orphaned,
found by AST because ruff's F841 does not flag a call-valued assignment.
Chose the plain helper over the decorator, as recommended: a decorator would
hide the ~600-patch-site indirection where a reader could not see it. Line
count is roughly flat (-9); the win is DRY. The earlier "-68..-102 lines"
estimate was for the decorator form and was wrong for this one.
```

### R7 · Long parameter list · write_issue_file
```
closed 2026-09-01 — IssueFrontmatter parameter object; 17 params -> 4. Fourteen
of the seventeen existed only to assemble one front-matter dict, and to_dict()
now owns the "always present" vs "only when set" distinction. 48 call sites
rewritten by codemod, then rewrapped (it emitted lines up to 577 chars).
Behaviour proved beyond the suite: an issue written with every field populated
is byte-identical to the previous implementation's output, YAML key order
included. That mattered because the file is a stored format.
```

### R17 · Duplicate setup · create_server() with no fixture
```
closed 2026-09-01 — 228 calls at 29ms = 7.18s of a 9.18s suite. Now one shared
instance: suite 9.48s -> 1.93s, coverage unchanged at 91.14%.
Safe because tool bodies resolve get_workspace_root() at call time, so later
patches still apply. _state is the part that is not safe, so the template
snapshots _LOADED_EXTENSIONS/_PLUGIN_WARNINGS and every handout restores them.
@pytest.mark.fresh_server opts out; exactly one test needs it.
Installed at conftest import time, not in a fixture — `from terminal_hub.server
import create_server` binds at module import, before fixtures run.
Order-independence checked with pytest-randomly seeds 1/42/7.
```

### R8 · Long method · the _do_* cluster — complete
```
closed 2026-09-01 — the five that R8a could not prove, refactored after R21
supplied the coverage:
  get_runtime_state                 77 -> 36 stmts  (depth 4 -> 1)
  _do_sync_github_issues            72 -> 38
  _do_generate_milestone_knowledge  65 -> 39
  _do_generate_issue_workflows      59 -> 37  (depth 5 -> 1)
  _extract_design_refs              39 -> 18  (depth 5 -> 3)
No non-registry body in scope now exceeds 40 statements. _extract_design_refs
also lost its `in_principles` control flag — extracting the scan made the flag
local to it, which is Remove Control Flag falling out of Extract Method rather
than being applied separately.
Six stale imports dropped as a side effect.
```

### R21 · Tests · characterisation coverage for the R8 remainder
```
closed 2026-09-01 — 17 tests, written before any of the code they cover was
touched:
  _extract_design_refs              84.6% -> 100.0%
  _do_generate_milestone_knowledge  78.5% -> 100.0%
  _do_generate_issue_workflows      91.5% -> 100.0%
  _do_sync_github_issues            94.6% -> 100.0%
  get_runtime_state                 83.8% ->  96.2%
get_runtime_state keeps 3 unhit lines: two are an ImportError guard around an
optional cache import, one an else that the config schema makes unreachable.
Suite 1067 -> 1084 tests, coverage 89.72% -> 91.11%.
```

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
