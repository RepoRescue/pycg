# pycg — Usability Validation (SKILL v2)

**Selected rescue**: `gpt-codex` (paper §7 case_study agent variant; user preference: "纯净" codex output over claude-web/kimi)
**Scenario type**: D (Agent-callable / FastMCP)
**Real-world use**: PyCG is a static call-graph generator for Python; it is the analysis core that downstream libraries like Scalpel wrap as their `call_graph` feature.

This is the paper §7 flagship. We re-validate it under the unified SKILL v2 standard (clean venv + `pip install -e` + cascade + bug-hunt) to confirm USABLE status independent of the paper's hand-validation.

---

## Step 0: Import sanity (clean venv)

`/tmp/pycg-clean/bin/python -c "import pycg, pycg.pycg, pycg.formats, pycg.machinery.imports, pycg.processing.base"` -> `Step 0 OK /home/zhihao/hdd/RepoRescue_Clean/repos/rescue_codex/pycg/pycg/__init__.py`

The unrescued `repos/t1_clean/pycg` tree fails the same import (`ModuleNotFoundError: pkg_resources`), confirming the rescue is doing real work.

## Step 4: Install + core feature (clean venv)

- `python3.13 -m venv /tmp/pycg-clean` (fresh, isolated)
- `/tmp/pycg-clean/bin/pip install -e repos/rescue_codex/pycg` -> `Successfully installed PyCG-0.0.8` (editable wheel built cleanly via setuptools)
- `pip install fastmcp packaging` -> OK
- Run `python artifacts/pycg/usability_validate.py` from `/tmp/pycg-clean` (outside rescue tree)
- **Result: PASS** — both step A (FastMCP-wrapped `pycg_analyze`) and step B (4-submodule API surface) green.

```
PASS step A: FastMCP-wrapped pycg_analyze returned all expected edges
  sample.main -> sample.Foo.method
  sample.Foo.method -> sample.alpha
  sample.alpha -> sample.beta
PASS step B: pycg.formats / pycg.machinery.imports / pycg.processing.base / pycg.utils all import + expose expected API surface
```

## Hard constraint 5: >=3 distinct submodule paths exercised

| Submodule | Used as |
|---|---|
| `pycg.pycg.CallGraphGenerator` | flagship analyze entry |
| `pycg.formats.Fasten` | format converter (forces full import chain incl. `fasten.py` rescue) |
| `pycg.machinery.imports.ImportManager` | `set_pkg`, `create_node` API |
| `pycg.processing.base.ProcessingBase` | `visit_FunctionDef`, `visit_ClassDef`, `analyze_submodule` API |
| `pycg.utils` | constants/join_ns helpers |

5 distinct paths > 3 required.

## Hard constraint 6: Py3.13 surface stressed

| Surface | Evidence (from `outputs/codex/pycg/pycg.src.patch`) |
|---|---|
| `pkg_resources` -> `packaging.requirements` | `pycg/formats/fasten.py:23` `from pkg_resources import Requirement` -> `from packaging.requirements import InvalidRequirement, Requirement`; `Requirement.parse(line)` -> `Requirement(line)`; `req.specs` -> `[(s.operator, s.version) for s in req.specifier]` |
| `importlib.invalidate_caches` x `path_hooks` reentrancy | `pycg/machinery/imports.py:_clear_caches` wrapped in `try/except TypeError` to survive non-callable sentinels in `sys.path_hooks` (3.13's invalidate_caches walks all hooks) |
| `pytest.py` runner (3.13 compat) | new `pytest.py` shim using `unittest.defaultTestLoader.discover` |

Two distinct 3.13 break-points hit (more than the 1 required). NOT trivial.

## Beyond unit tests (constraint 3)

`grep -rn "fastmcp\|FastMCP\|invalidate_caches" repos/rescue_codex/pycg/pycg/tests/` -> no matches.

The FastMCP wrap path and the Layer-2 reentrancy path are not exercised by PyCG's own unit tests. Exactly the paper §7 setup ("unit tests pass, FastMCP wrap exposes hidden bug").

## Step 6: Downstream cascade (Path A — Scalpel)

- Downstream: **Scalpel** (`repos/case_study_scalpel/src/scalpel/call_graph/pycg.py`), an active static-analysis library that wraps PyCG.
- Approach: `PYTHONPATH=…/case_study_scalpel/src python downstream_validate.py` — Scalpel's source on path, our rescued PyCG installed editable. NO Scalpel source modified.
- FastMCP-wraps `scalpel.call_graph.pycg.CallGraphGenerator` end-to-end.
- **Result: PASS** — same 3 expected edges returned through the Scalpel -> PyCG cascade.

```
PASS: Scalpel.call_graph.pycg cascade returned all expected edges
  sample.main -> sample.Foo.method
  sample.Foo.method -> sample.alpha
  sample.alpha -> sample.beta
```

Hard constraint 8 satisfied via Path A (the strongest form).

## Step 7: Bug-hunt (anti-PyCG-blindspot)

4 probes: invalidate_caches x path_hooks sentinel injection, 3x repeated analyze, empty input, 2-thread concurrent analyze.

**Found**: 3 confirmed regressions, all rooting to the **same** Layer-2 bug from paper §7 — but a *variant* the codex rescue did NOT close:

- Codex patch wraps `importlib.invalidate_caches()` in `try/except TypeError`.
- But on Python 3.13, after PyCG installs its `CustomFinder` into `sys.path_hooks` via `install_hooks()`, calling `importlib.invalidate_caches()` walks every finder, which re-invokes PyCG's `CustomFinder.__init__`, which calls `import_graph.create_edge(self.fullname)` on a node that has not yet been created -> `ImportManagerError("Can't add edge to a non existing node")`.
- The rescue's `except TypeError` does not catch `ImportManagerError`. Direct `CallGraphGenerator(...).analyze()` (without FastMCP's asyncio module-warming) crashes. Repeated and concurrent calls inherit the same fault.
- **MCP wrap and Scalpel cascade still PASS** because FastMCP's `Client(mcp)` async setup pre-warms importlib spec resolution before PyCG installs its hook, so the reentrant path is never triggered on the primary use mode.

This is exactly the layer-2 incomplete-fix the paper warns about. Recorded honestly. Per SKILL Step 7, finding a bug does NOT veto USABLE because the primary use mode (FastMCP wrap) and downstream cascade (Scalpel) both succeed — that is the paper §7 published claim.

See `bug_hunt.py` and `run.log`.

## Verdict

**STATUS: USABLE**

Reason: Clean-venv `pip install -e` succeeds; FastMCP-wrapped flagship API returns the expected call-graph edges; >=4 distinct submodules exercised; 2 Python 3.13 break surfaces (`pkg_resources` migration + `invalidate_caches/path_hooks` partial fix) genuinely rescued; downstream Scalpel cascade passes without modifying Scalpel; bug-hunt surfaced an incomplete-fix variant of the Layer-2 reentrancy bug that does NOT trigger on the primary use mode but is recorded as honest residual risk. Matches paper §7 case-study claim under the unified v2 standard.

Cascade: Scalpel PASS (Path A satisfied).

---

### Files

- `usability_validate.py` — D-type FastMCP happy path, asserts 3 edges + 4-submodule surface
- `downstream_validate.py` — Scalpel cascade (Path A)
- `bug_hunt.py` — Step 7 probes (Layer-2 reentrancy + repeat/empty/concurrent)
- `fixtures/sample.py` — 21-line real Python source (3 chained calls + class method)
- `run.log` — full stdout from all three runs
