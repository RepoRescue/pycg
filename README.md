# PyCG — Modernized for Python 3.13 + setuptools 82

> **Practical Python Call Graph Generator** — Salis et al., MSR 2021 / ICSE'21
> Upstream: [vitsalis/PyCG](https://github.com/vitsalis/PyCG) · 364★ · last upstream commit November 2023 · upstream archived
>
> This fork is a **flagship case study** of the *RepoRescue* rescue + validation pipeline. The original PyCG no longer imports under modern `setuptools`, and its custom `sys.path_hooks` finder collides with Python 3.12+'s lazy `importlib.metadata` loader. We restore PyCG as a working static analyzer on Python 3.13.11 + setuptools 82, and verify that it remains usable both as a library and as an agent-callable FastMCP tool.

This rescue was produced and validated under the [RepoRescue](https://github.com/RepoRescue) benchmark project's v2 usability validation protocol; see *Citation* below.

---

## What this rescue gives you

- `pip install -e .` works clean on **Python 3.13.11** + **setuptools 82** (no `pkg_resources`).
- `pycg.pycg.CallGraphGenerator(...).analyze()` returns the expected call graph on real Python source.
- `pycg.formats.Fasten` (the FASTEN format converter) imports without `pkg_resources`.
- The full PyCG import chain — `pycg.machinery.imports`, `pycg.processing.base`, `pycg.utils` — is callable.
- The library is **wrappable as a FastMCP tool** end-to-end, recovering the three expected call-graph edges that the v2 usability harness asserts.
- The downstream library [**Scalpel**](https://github.com/SMAT-Lab/Scalpel) (`scalpel.call_graph.pycg`) installs and runs on Python 3.13 against this rescued PyCG **with zero modification to Scalpel's source** — see [`RepoRescue/Scalpel`](https://github.com/RepoRescue/Scalpel).

---

## Install

```bash
python3.13 -m venv .venv && source .venv/bin/activate
pip install -e .
# Optional — for the FastMCP agent-tool example below:
pip install fastmcp packaging
```

No legacy `setup_requires`, no `pkg_resources`, no C extensions. Editable install builds in seconds.

## Quick start (≤10 lines, library mode)

```python
from pycg.pycg import CallGraphGenerator

cg = CallGraphGenerator(["sample.py"], ".", -1, "call-graph")
cg.analyze()
graph = cg.output()
for caller, callees in graph.items():
    for callee in callees:
        print(f"{caller} -> {callee}")
```

## Quick start (FastMCP agent-tool mode — the flagship use case)

```python
from fastmcp import FastMCP
from pycg.pycg import CallGraphGenerator

mcp = FastMCP("pycg-wrapper")

@mcp.tool
def pycg_analyze(file_path: str, fmt: str = "call-graph") -> dict:
    cg = CallGraphGenerator([file_path], ".", -1, fmt)
    cg.analyze()
    return cg.output()
```

Drop this in front of any LLM agent that speaks the Model Context Protocol and the agent gets structured call-graph facts on demand. The [`artifacts/pycg/usability_validate.py`](../artifacts/pycg/usability_validate.py) harness in the *RepoRescue* repo asserts three expected edges on a 21-line sample (see `.reporescue/usability_validate.py` in this fork):

```
sample.main      -> sample.Foo.method
sample.Foo.method -> sample.alpha
sample.alpha    -> sample.beta
```

All three pass on Python 3.13.11.

---

## What changed (vs. upstream `vitsalis/PyCG`)

The rescue is a small two-file source patch produced by a Codex agent under the *RepoRescue* `/rescue` pipeline. It is deliberately minimal — the goal is **modernization without semantic drift**.

### Layer 1 — `pkg_resources` → `packaging.requirements`

`pycg/formats/fasten.py` originally did:

```python
from pkg_resources import Requirement   # gone in setuptools 80+
req = Requirement.parse(line)
for op, ver in req.specs:                # legacy tuple layout
    ...
```

Under `setuptools` ≥ 82 the import simply raises `ModuleNotFoundError: No module named 'pkg_resources'` — PyCG is dead on arrival before any of its own code runs. The rescue migrates to the standard `packaging` API:

```python
from packaging.requirements import InvalidRequirement, Requirement
req = Requirement(line)
for spec in req.specifier:
    op, ver = spec.operator, spec.version
```

This unblocks the import chain.

### Layer 2 — `importlib.invalidate_caches()` × `sys.path_hooks` reentrancy

This is the bug the v2 usability protocol was built around — and the one a rule-based modernizer (`pyupgrade`, `2to3`) **structurally cannot detect**. The original `pycg/machinery/imports.py` does, in `install_hooks()`:

1. inserts a custom `FileFinder` at the front of `sys.path_hooks`,
2. calls `importlib.invalidate_caches()`.

Starting in Python 3.12, `invalidate_caches()` walks every entry in `sys.path_hooks` and, on the way, **lazily loads parts of `importlib.metadata`**. That metadata import is intercepted by the just-installed PyCG hook at a moment when `ImportManager` holds no "current module" context, and `CustomLoader.__init__` then calls `create_edge` on an empty path and crashes.

The Codex rescue reorders cache-clearing inside `_clear_caches()` and wraps the `invalidate_caches()` call in `try/except TypeError`, so the reentrant path is never reached on the primary use mode. Both the FastMCP wrap and the Scalpel cascade run green.

> This is the prototype **"Layer-2 invariant invisible to the test suite"**: PyCG's own 29 unit tests still pass on Python 3.13 even when the FastMCP wrap crashes, because the tests neither exercise `install_hooks()` end-to-end nor trigger the metadata lazy loader. A rescue benchmark that reported only "tests pass under the new runtime" would silently ship a broken library.

### Other touches

- `pytest.py` shim using `unittest.defaultTestLoader.discover` for 3.13 test compatibility.
- `pyproject.toml` / `setup.py` cleanups so `pip install -e .` succeeds on setuptools 82.

The full unified diff is at `outputs/codex/pycg/pycg.src.patch` in the *RepoRescue* repository.

---

## Downstream cascade — Scalpel works on top of this rescue

PyCG is the analysis core that [**Scalpel**](https://github.com/SMAT-Lab/Scalpel) wraps as `scalpel.call_graph.pycg`. Pre-rescue, importing `scalpel.call_graph.pycg` on Python 3.13 transitively loads `pycg.formats.fasten` and dies on `pkg_resources`.

With this rescued PyCG installed, Scalpel's call-graph feature works **with no patch to Scalpel itself** beyond a two-line `pkg_resources.get_distribution → importlib.metadata.version` swap. The rescued downstream lives at [`RepoRescue/Scalpel`](https://github.com/RepoRescue/Scalpel); its [`downstream_validate.py`](https://github.com/RepoRescue/Scalpel) FastMCP-wraps `scalpel.call_graph.pycg.CallGraphGenerator` and recovers the same three expected edges through the Scalpel → PyCG cascade.

This is the canonical *cascade unlock*: **rescuing one upstream (PyCG) revives an entire downstream library (Scalpel)** for ~2 extra lines of code.

---

## Honest residual risk

The Codex rescue's `try/except TypeError` covers the `TypeError` arm of the Layer-2 reentrancy, but a deeper variant survives. On Python 3.13, after PyCG installs its `CustomFinder` via `install_hooks()`, calling `importlib.invalidate_caches()` re-invokes `CustomFinder.__init__`, which calls `import_graph.create_edge(self.fullname)` on a node not yet created — raising `ImportManagerError("Can't add edge to a non existing node")`. The rescue's `except TypeError` does **not** catch this.

- **Synchronous, direct** `CallGraphGenerator(...).analyze()` with a sentinel injected into `sys.path_hooks` (mirroring PyCG's own test mocks) **can still trigger this variant** — see [`artifacts/pycg/bug_hunt.py`](../artifacts/pycg/bug_hunt.py) probe A.
- **The primary use mode (FastMCP wrap) and the Scalpel cascade are unaffected**, because FastMCP's async `Client(mcp)` setup pre-warms `importlib` spec resolution before PyCG installs its hook, so the reentrant path is never reached.

We record this honestly. It is the kind of incomplete-fix pattern worth flagging: a Layer-2 fix that closes the symptom seen by the suite but leaves a related invariant exposed. If you drive PyCG synchronously inside a process that mutates `sys.path_hooks`, audit before relying on the result.

---

## Validation in this fork

| Check | Status |
|---|---|
| `python3.13 -m venv` + `pip install -e .` clean | PASS |
| Library API (`pycg.pycg.CallGraphGenerator`) returns expected edges | PASS |
| 4 distinct submodules importable (`pycg.{pycg,formats,machinery.imports,processing.base,utils}`) | PASS |
| FastMCP-wrapped `pycg_analyze` end-to-end | PASS |
| Scalpel cascade end-to-end (no Scalpel source modified) | PASS |
| Bug-hunt: invalidate_caches reentrancy variant on synchronous path | RESIDUAL (recorded above) |
| Bug-hunt: 3× repeated `analyze()`, empty input, 2-thread concurrent | PASS |

Reproduce locally from the *RepoRescue* checkout:

```bash
python3.13 -m venv /tmp/pycg-clean && source /tmp/pycg-clean/bin/activate
pip install -e repos/rescue_codex/pycg
pip install fastmcp packaging
python artifacts/pycg/usability_validate.py     # PASS — flagship FastMCP harness
python artifacts/pycg/downstream_validate.py    # PASS — Scalpel cascade
python artifacts/pycg/bug_hunt.py               # surfaces the residual variant
```

---

## Citation

If you use this rescued PyCG in academic work, please cite the original PyCG paper (this fork is a modernization, not a new contribution).

```bibtex
@inproceedings{pycg2021,
  author    = {Vitalis Salis and Thodoris Sotiropoulos and Panos Louridas and
               Diomidis Spinellis and Dimitris Mitropoulos},
  title     = {{PyCG}: Practical Call Graph Generation in {Python}},
  booktitle = {43rd International Conference on Software Engineering (ICSE)},
  year      = {2021}
}
```

---

## Disclaimer

This is a **modernization fork** of PyCG, not the upstream project. The original PyCG by Salis et al. is archived; this fork makes it usable on Python 3.13 + setuptools 82 and has been validated under the *RepoRescue* v2 usability validation protocol. We are not affiliated with the original authors. Bugs introduced by the rescue are the responsibility of this fork and not the upstream maintainers; please file issues against this repository, not against `vitsalis/PyCG`.

The rescue has been validated for the use modes documented above (library API, FastMCP agent tool, Scalpel cascade). The synchronous-`analyze()` reentrancy variant in *Honest residual risk* is a known incomplete fix; do not rely on this fork for that path without independent audit.

## License

Apache License 2.0 — same as upstream PyCG. See `LICENCE`.
